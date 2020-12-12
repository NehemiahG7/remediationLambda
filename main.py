import os
import yaml
import boto3
from kubernetes import client, config
import auth
import json
import time

#COMMAND TO PRINT LOG TO AWS CLI
"""aws lambda invoke --function-name apiTest out --log-type Tail \
--query 'LogResult' --output text |  base64 -d
"""
#Location of kubeconfig file inside lambda 
KUBE_FILEPATH = '/tmp/kubeconfig'
  
# Configure your cluster name and region here
CLUSTER_NAME = ''
REGION = ''
kube_content = dict()

#PRINT OUT FOR STATUS OF PODS
PPODS="DISPLAYING PODS"
DPODS="DEPLOYMENT ROLLBACK IN PROGRESS..."

#podDeletePolicy takes the event payload from awsAPIGateway and a connect to eks to delete the target pods specified in the event.    
def podDeletePolicy(obj, api):
    v1 = client.CoreV1Api(api)
    for i in obj["targets"]:
        #Parse name string and assign required values
        n = i["name"].split(":")
        namespace = n[2]
        pod = n[3]
        print("Target: ", pod)
        resp = v1.delete_namespaced_pod(pod, namespace)
        print(resp)

#rollbackDeploymentPolicy
def rollbackDeploymentPolicy(obj, api):
    #check if alert has been duplicated
    if getLabels(obj, api) == "v1":
        print("Duplicate alert")
        return

    api_instance = client.AppsV1beta1Api(api)
    #Parse name string and assign required values
    n = getName(obj)
    namespace = n[2]
    deployment = n[4]

    #Parse deployment name to remove suffix
    n = deployment.split("-")
    deployment = n[0]+"-"+n[1]+"-"+n[2]
    body = client.AppsV1beta1DeploymentRollback(None,None,deployment, client.AppsV1beta1RollbackConfig())
    print("Target: ", deployment)
    resp = api_instance.create_namespaced_deployment_rollback(deployment, namespace, body)
    print(resp)

#getLabels to filter out duplicate alerts for demo
def getLabels (obj, api):
    con = client.CoreV1Api(api)
    ret = con.list_namespaced_pod("demo")
    v1 = 0
    v2 = 0
    for i in ret.items:
        print(i.metadata.labels["version"])
        version = i.metadata.labels["version"]
        if version == "v1":
            v1 += 1
        elif version == "v2":
            v2 += 1
        else:
            print("Unrecognized version", version)
    if v1 == 2:
        return "v1"
    if v2 == 2:
        return "v2"

def getName(obj):
    return obj["targets"][0]["name"].split(":")
    



#printContent takes an event from apiGateway and prints it to the screen
def printContent(obj):
    for i in obj.keys():
        print(i, ": ",obj[i])


#Dict to act as switch statement using policy names as keys and remediation functions as values
options = {
    
    
    #Note, all options delete the given pods
    "demoApplicationCPU": podDeletePolicy,
    "demoApplicationMemory": podDeletePolicy,
    "New Relic Alert - Test Policy": podDeletePolicy,
    "remediationDemoPolicy": rollbackDeploymentPolicy,
    "getLabels": getLabels
}
    
 

    

def handler(event, context):

    #check if issue has already been closed
    if event["current_state"] == "closed":
        print("Issue already closed")
        return {
        'statusCode': 200,
        'body': json.dumps('Issue already closed')
    }

    # Config cluster name and region
    global CLUSTER_NAME
    CLUSTER_NAME = getName(event)[1]
    global REGION
    REGION = event["region"]

    # We assume that when the Lambda container is reused, a kubeconfig file exists.
    # If it does not exist, it creates the file.
    if not os.path.exists(KUBE_FILEPATH):
        global kube_content
        print("In KUBE_FILEPATH")
        
        
        # Get data from EKS API
        eks_api = boto3.client('eks',region_name=REGION)
        cluster_info = eks_api.describe_cluster(name=CLUSTER_NAME)
        
        
        #fetches certificate from eks api
        certificate = cluster_info['cluster']['certificateAuthority']['data']
        endpoint = cluster_info['cluster']['endpoint']
        
        
        # Generating kubeconfig
        kube_content = dict()
        kube_content['apiVersion'] = 'v1'
        kube_content['clusters'] = [
            {
            'cluster':
                {
                'server': endpoint,
                'certificate-authority-data': certificate
                },
            'name':'kubernetes'        
            }]
        kube_content['contexts'] = [
            {
            'context':
                {
                'cluster':'kubernetes',
                'user':'aws'
                },
            'name':'aws'
            }]
        kube_content['current-context'] = 'aws'
        kube_content['Kind'] = 'config'
        kube_content['users'] = [
        {
        'name':'aws',
        'user':'lambda'
        }]


        # create kubeconfig file in kube_content object
        #the write to '/tmp/kubeconfig' the contents of kube_content, the location is inside the lambda function
        #Write out the yaml configuration file to /tmp since lambda is read-only
        with open(KUBE_FILEPATH, 'w') as outfile:
            yaml.dump(kube_content, outfile, default_flow_style=False)

    # Get bearer token hash
    eks = auth.EKSAuth(CLUSTER_NAME)
    token = eks.get_token()
    
    
    # Loads authentication and cluster information from kube-config file
    #and stores them in kubernetes.client.configuration.
    config.load_kube_config(KUBE_FILEPATH)

    
    #This class is auto generated by OpenAPI Generator
    configuration = client.Configuration()
    
    
    #dict to store API key(s) which is our token
    configuration.api_key['authorization'] = token
    
    
    #dict to store API prefix (e.g. Bearer)
    configuration.api_key_prefix['authorization'] = 'Bearer'


    # API
    #OpenAPI generic API client. This client handles the client-
    #server communication, and is invariant across implementations.
    api = client.ApiClient(configuration)
    v1 = client.CoreV1Api(api)

 
    
    # Get all the pods in a specific name space
    #list or watch objects of kind Pod
    ret = v1.list_namespaced_pod("demo")

    #Print event payload
    print("##Event Payload##")
    printContent(event)
    print("##Event Payload##")
    
    
    #Print pods to log for debug and demo purpose
    print(PPODS.center(50, '*'))
    for i in ret.items:
        print("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))
    print(PPODS.center(50, '*'))
    
    
    #DELETING PODS ON ALERT
    print(DPODS.center(50, '*'))
    name = event["policy_name"]
    options[name](event, api)
    print(DPODS.center(50, '*'))
    
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }

    
        