import json
from app.database import get_db, get_db_session
from app.db.connection import get_user_connections_by_type
from minio import Minio
from minio.error import S3Error
from app.schemas.workspace_status import WorkspaceStatusCreate
from app.db.workspace_status import create_or_update_workspace_status
from app.db.workspace import create_or_update_workspace
from app.schemas.workspace import WorkspaceCreate

import os
from dotenv import load_dotenv
import openai
import boto3
import shutil
import re
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.model import ServiceModel
from openai import OpenAI
from datetime import datetime, date 
import boto3
from app.models.connection import Connection

import subprocess
# Load API key from .env
load_dotenv()
client = OpenAI()
openai.api_key = os.getenv("OPENAI_API_KEY")


TEMP_DIR = os.path.abspath("temp")
os.makedirs(TEMP_DIR, exist_ok=True)


def get_s3_connection_info_with_credentials(user_id):
    """
    Fetches S3 backend info for Terraform remote state + AWS credentials.

    Returns:
        dict: {
            "bucket": str,
            "region": str,
            "prefix": str,
            "aws_access_key_id": str,
            "aws_secret_access_key": str
        }
    """
    result = {
        "bucket": None,
        "region": "us-east-1",
        "prefix": "",
        "aws_access_key_id": None,
        "aws_secret_access_key": None
    }

    with get_db_session() as db:
        # Fetch S3 remote state connection
        s3_conn = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == "aws_s3_remote_state"
        ).first()

        if not s3_conn:
            raise Exception("No S3 remote state connection found for user")

        s3_json = s3_conn.connection_json
        if isinstance(s3_json, str):
            try:
                s3_json = json.loads(s3_json)
            except json.JSONDecodeError:
                raise Exception("Invalid first-level JSON in S3 connection_json")
        if isinstance(s3_json, str):
            try:
                s3_json = json.loads(s3_json)
            except json.JSONDecodeError:
                raise Exception("Invalid second-level JSON in S3 connection_json")

        s3_info = {item["key"]: item["value"] for item in s3_json}
        result["bucket"] = s3_info.get("BUCKET_NAME")
        result["region"] = s3_info.get("AWS_REGION", result["region"])
        result["prefix"] = s3_info.get("PREFIX", result["prefix"])

        # Fetch AWS credentials
        aws_conn = db.query(Connection).filter(
            Connection.userid == user_id,
            Connection.type == "aws"
        ).first()

        if aws_conn:
            aws_json = aws_conn.connection_json
            if isinstance(aws_json, str):
                try:
                    aws_json = json.loads(aws_json)
                except json.JSONDecodeError:
                    raise Exception("Invalid first-level JSON in AWS connection_json")
            if isinstance(aws_json, str):
                try:
                    aws_json = json.loads(aws_json)
                except json.JSONDecodeError:
                    raise Exception("Invalid second-level JSON in AWS connection_json")

            aws_info = {item["key"]: item["value"] for item in aws_json}
            result["aws_access_key_id"] = aws_info.get("AWS_ACCESS_KEY_ID")
            result["aws_secret_access_key"] = aws_info.get("AWS_SECRET_ACCESS_KEY")
            # If region wasn't set in S3 config, take from credentials
            result["region"] = result["region"] or aws_info.get("AWS_REGION", result["region"])

    return result



def get_aws_credentials_from_db(user_id: int) -> tuple[str, str]:
    """
    Fetch AWS credentials from the database for a given user.
    
    Args:
        user_id (int): ID of the user to fetch credentials for (default: 5)
    
    Returns:
        Tuple of (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    
    Raises:
        ValueError if credentials are not found or incomplete.
    """
    with get_db_session() as db:
        connections = get_user_connections_by_type(db, user_id, "aws")
        if not connections:
            raise ValueError("❌ No AWS connection found for user")

        connection = connections[0]
        connection_data = json.loads(connection.connection_json)

        aws_access_key = next(
            (item["value"] for item in connection_data if item["key"] == "AWS_ACCESS_KEY_ID"),
            None
        )
        aws_secret_key = next(
            (item["value"] for item in connection_data if item["key"] == "AWS_SECRET_ACCESS_KEY"),
            None
        )

        if not aws_access_key or not aws_secret_key:
            raise ValueError("❌ AWS credentials are incomplete")
        print(aws_access_key, aws_secret_key)
        return aws_access_key, aws_secret_key


class DynamicAWSResourceInspector:
    def __init__(self, access_key, secret_key, region='us-east-1'):
        self.session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        self.region = region
        
        # Cache for service clients
        self._clients = {}
        
        # Common describe/get operation patterns
        self.operation_patterns = {
            'describe': ['describe_', 'get_', 'list_'],
            'resource_patterns': {
                'instance': ['instances', 'instance'],
                'volume': ['volumes', 'volume'],
                'vpc': ['vpcs', 'vpc'],
                'subnet': ['subnets', 'subnet'],
                'security-group': ['security_groups', 'security_group'],
                'key-pair': ['key_pairs', 'key_pair'],
                'image': ['images', 'image'],
                'snapshot': ['snapshots', 'snapshot'],
                'network-interface': ['network_interfaces', 'network_interface'],
                'route-table': ['route_tables', 'route_table'],
                'internet-gateway': ['internet_gateways', 'internet_gateway'],
                'bucket': ['buckets', 'bucket'],
                'function': ['functions', 'function'],
                'role': ['roles', 'role'],
                'user': ['users', 'user'],
                'policy': ['policies', 'policy'],
                'table': ['tables', 'table'],
                'cluster': ['clusters', 'cluster'],
                'db': ['db_instances', 'db_instance'],
                'topic': ['topics', 'topic'],
                'queue': ['queues', 'queue'],
                'stack': ['stacks', 'stack'],
                'alarm': ['alarms', 'alarm'],
                'secret': ['secrets', 'secret'],
                'parameter': ['parameters', 'parameter'],
                'key': ['keys', 'key'],
                'distribution': ['distributions', 'distribution'],
                'file-system': ['file_systems', 'file_system'],
                'log-group': ['log_groups', 'log_group'],
                'loadbalancer': ['load_balancers', 'load_balancer'],
                'autoScalingGroup': ['auto_scaling_groups', 'auto_scaling_group'],
                'hostedzone': ['hosted_zones', 'hosted_zone'],
                'restapis': ['rest_apis', 'rest_api'],
                # New resource patterns
                'notebook-instance': ['notebook_instances', 'notebook_instance'],
                'model': ['models', 'model'],
                'endpoint': ['endpoints', 'endpoint'],
                'training-job': ['training_jobs', 'training_job'],
                'service': ['services', 'service'],
                'task': ['tasks', 'task'],
                'repository': ['repositories', 'repository'],
                'workgroup': ['workgroups', 'workgroup'],
                'database': ['databases', 'database'],
                'crawler': ['crawlers', 'crawler'],
                'job': ['jobs', 'job'],
                'application': ['applications', 'application'],
                'environment': ['environments', 'environment'],
                'state-machine': ['state_machines', 'state_machine'],
                'rule': ['rules', 'rule'],
                'detector': ['detectors', 'detector'],
                'finding': ['findings', 'finding'],
                'budget': ['budgets', 'budget'],
                'report': ['reports', 'report']
            }
        }
        
        # Enhanced service-specific parameter mappings
        self.service_mappings = {
            'ec2': {
                'instance': {'operation': 'describe_instances', 'param': 'InstanceIds', 'list_param': True},
                'volume': {'operation': 'describe_volumes', 'param': 'VolumeIds', 'list_param': True},
                'vpc': {'operation': 'describe_vpcs', 'param': 'VpcIds', 'list_param': True},
                'subnet': {'operation': 'describe_subnets', 'param': 'SubnetIds', 'list_param': True},
                'security-group': {'operation': 'describe_security_groups', 'param': 'GroupIds', 'list_param': True},
                'key-pair': {'operation': 'describe_key_pairs', 'param': 'KeyNames', 'list_param': True},
                'image': {'operation': 'describe_images', 'param': 'ImageIds', 'list_param': True},
                'snapshot': {'operation': 'describe_snapshots', 'param': 'SnapshotIds', 'list_param': True},
                'network-interface': {'operation': 'describe_network_interfaces', 'param': 'NetworkInterfaceIds', 'list_param': True},
                'route-table': {'operation': 'describe_route_tables', 'param': 'RouteTableIds', 'list_param': True},
                'internet-gateway': {'operation': 'describe_internet_gateways', 'param': 'InternetGatewayIds', 'list_param': True}
            },
            'rds': {
                'db': {'operation': 'describe_db_instances', 'param': 'DBInstanceIdentifier', 'list_param': False},
                'cluster': {'operation': 'describe_db_clusters', 'param': 'DBClusterIdentifier', 'list_param': False},
                'snapshot': {'operation': 'describe_db_snapshots', 'param': 'DBSnapshotIdentifier', 'list_param': False}
            },
            'lambda': {
                'function': {'operation': 'get_function', 'param': 'FunctionName', 'list_param': False}
            },
            'iam': {
                'role': {'operation': 'get_role', 'param': 'RoleName', 'list_param': False},
                'user': {'operation': 'get_user', 'param': 'UserName', 'list_param': False},
                'policy': {'operation': 'get_policy', 'param': 'PolicyArn', 'list_param': False}
            },
            'dynamodb': {
                'table': {'operation': 'describe_table', 'param': 'TableName', 'list_param': False}
            },
            'sns': {
                'topic': {'operation': 'get_topic_attributes', 'param': 'TopicArn', 'list_param': False}
            },
            'sqs': {
                'queue': {'operation': 'get_queue_attributes', 'param': 'QueueUrl', 'list_param': False}
            },
            'cloudformation': {
                'stack': {'operation': 'describe_stacks', 'param': 'StackName', 'list_param': False}
            },
            'cloudwatch': {
                'alarm': {'operation': 'describe_alarms', 'param': 'AlarmNames', 'list_param': True}
            },
            'logs': {
                'log-group': {'operation': 'describe_log_groups', 'param': 'logGroupNamePrefix', 'list_param': False}
            },
            'secretsmanager': {
                'secret': {'operation': 'describe_secret', 'param': 'SecretId', 'list_param': False}
            },
            'ssm': {
                'parameter': {'operation': 'get_parameter', 'param': 'Name', 'list_param': False}
            },
            'kms': {
                'key': {'operation': 'describe_key', 'param': 'KeyId', 'list_param': False}
            },
            'apigateway': {
                'restapis': {'operation': 'get_rest_api', 'param': 'restApiId', 'list_param': False}
            },
            'cloudfront': {
                'distribution': {'operation': 'get_distribution', 'param': 'Id', 'list_param': False}
            },
            'efs': {
                'file-system': {'operation': 'describe_file_systems', 'param': 'FileSystemId', 'list_param': False}
            },
            'elasticache': {
                'cluster': {'operation': 'describe_cache_clusters', 'param': 'CacheClusterId', 'list_param': False}
            },
            'redshift': {
                'cluster': {'operation': 'describe_clusters', 'param': 'ClusterIdentifier', 'list_param': False}
            },
            'autoscaling': {
                'autoScalingGroup': {'operation': 'describe_auto_scaling_groups', 'param': 'AutoScalingGroupNames', 'list_param': True}
            },
            'route53': {
                'hostedzone': {'operation': 'get_hosted_zone', 'param': 'Id', 'list_param': False}
            },
            'elb': {
                'loadbalancer': {'operation': 'describe_load_balancers', 'param': 'LoadBalancerNames', 'list_param': True}
            },
            'elbv2': {
                'loadbalancer': {'operation': 'describe_load_balancers', 'param': 'Names', 'list_param': True}
            },
            # NEW SERVICES ADDED
            'sagemaker': {
                'notebook-instance': {'operation': 'describe_notebook_instance', 'param': 'NotebookInstanceName', 'list_param': False},
                'model': {'operation': 'describe_model', 'param': 'ModelName', 'list_param': False},
                'endpoint': {'operation': 'describe_endpoint', 'param': 'EndpointName', 'list_param': False},
                'training-job': {'operation': 'describe_training_job', 'param': 'TrainingJobName', 'list_param': False},
                'endpoint-config': {'operation': 'describe_endpoint_config', 'param': 'EndpointConfigName', 'list_param': False}
            },
            'eks': {
                'cluster': {'operation': 'describe_cluster', 'param': 'name', 'list_param': False},
                'nodegroup': {'operation': 'describe_nodegroup', 'param': 'nodegroupName', 'list_param': False}
            },
            'ecs': {
                'cluster': {'operation': 'describe_clusters', 'param': 'clusters', 'list_param': True},
                'service': {'operation': 'describe_services', 'param': 'services', 'list_param': True},
                'task': {'operation': 'describe_tasks', 'param': 'tasks', 'list_param': True}
            },
            'ecr': {
                'repository': {'operation': 'describe_repositories', 'param': 'repositoryNames', 'list_param': True}
            },
            'athena': {
                'workgroup': {'operation': 'get_work_group', 'param': 'WorkGroup', 'list_param': False},
                'database': {'operation': 'get_database', 'param': 'DatabaseName', 'list_param': False}
            },
            'glue': {
                'database': {'operation': 'get_database', 'param': 'Name', 'list_param': False},
                'table': {'operation': 'get_table', 'param': 'Name', 'list_param': False},
                'crawler': {'operation': 'get_crawler', 'param': 'Name', 'list_param': False},
                'job': {'operation': 'get_job', 'param': 'JobName', 'list_param': False}
            },
            'emr': {
                'cluster': {'operation': 'describe_cluster', 'param': 'ClusterId', 'list_param': False}
            },
            'elasticbeanstalk': {
                'application': {'operation': 'describe_applications', 'param': 'ApplicationNames', 'list_param': True},
                'environment': {'operation': 'describe_environments', 'param': 'EnvironmentNames', 'list_param': True}
            },
            'appsync': {
                'graphqlApi': {'operation': 'get_graphql_api', 'param': 'apiId', 'list_param': False}
            },
            'stepfunctions': {
                'stateMachine': {'operation': 'describe_state_machine', 'param': 'stateMachineArn', 'list_param': False}
            },
            'events': {
                'rule': {'operation': 'describe_rule', 'param': 'Name', 'list_param': False}
            },
            'guardduty': {
                'detector': {'operation': 'get_detector', 'param': 'DetectorId', 'list_param': False}
            },
            'macie2': {
                'classification-job': {'operation': 'describe_classification_job', 'param': 'jobId', 'list_param': False}
            },
            'inspector': {
                'assessment-template': {'operation': 'describe_assessment_templates', 'param': 'assessmentTemplateArns', 'list_param': True}
            },
            'securityhub': {
                'hub': {'operation': 'get_enabled_standards', 'param': 'StandardsSubscriptionArns', 'list_param': True}
            },
            'config': {
                'configuration-recorder': {'operation': 'describe_configuration_recorders', 'param': 'ConfigurationRecorderNames', 'list_param': True}
            },
            'budgets': {
                'budget': {'operation': 'describe_budget', 'param': 'BudgetName', 'list_param': False}
            }
        }
        
        # Enhanced special handling for services
        self.special_handlers = {
            's3': self._handle_s3,
            'sns': self._handle_sns,
            'sqs': self._handle_sqs,
            'iam': self._handle_iam,
            'apigateway': self._handle_apigateway,
            'sagemaker': self._handle_sagemaker,
            'eks': self._handle_eks,
            'ecs': self._handle_ecs,
            'ecr': self._handle_ecr,
            'athena': self._handle_athena,
            'glue': self._handle_glue,
            'emr': self._handle_emr,
            'elasticbeanstalk': self._handle_elasticbeanstalk,
            'appsync': self._handle_appsync,
            'stepfunctions': self._handle_stepfunctions,
            'events': self._handle_events,
            'guardduty': self._handle_guardduty,
            'macie2': self._handle_macie,
            'inspector': self._handle_inspector,
            'securityhub': self._handle_securityhub,
            'config': self._handle_config,
            'budgets': self._handle_budgets,
            'ce': self._handle_cost_explorer
        }
    
    def get_client(self, service_name, region=None):
        """Get or create a boto3 client for the service"""
        if region is None:
            region = self.region
        
        client_key = f"{service_name}_{region}"
        if client_key not in self._clients:
            self._clients[client_key] = self.session.client(service_name, region_name=region)
        return self._clients[client_key]
    
    def parse_arn(self, arn):
        """Parse ARN into components"""
        try:
            parts = arn.split(':')
            if len(parts) < 6:
                return None
            
            return {
                'partition': parts[1],
                'service': parts[2],
                'region': parts[3],
                'account': parts[4],
                'resource': parts[5],
                'full_arn': arn
            }
        except Exception:
            return None
    
    def extract_resource_info(self, resource_part):
        """Extract resource type and ID from resource part of ARN"""
        if '/' in resource_part:
            # Format: type/id or type/subtype/id
            parts = resource_part.split('/')
            if len(parts) >= 2:
                return {
                    'type': parts[0],
                    'id': '/'.join(parts[1:]),
                    'full_resource': resource_part
                }
        elif ':' in resource_part:
            # Format: type:id
            parts = resource_part.split(':', 1)
            return {
                'type': parts[0],
                'id': parts[1],
                'full_resource': resource_part
            }
        else:
            # Just the resource ID (common for S3)
            return {
                'type': 'bucket' if resource_part else 'unknown',
                'id': resource_part,
                'full_resource': resource_part
            }
    
    def discover_operations(self, client, resource_type, resource_id):
        """Dynamically discover available operations for a resource"""
        operations = []
        
        # Get all operations for this service
        service_model = client._service_model
        operation_names = service_model.operation_names
        
        # Find operations that might be relevant
        for op_name in operation_names:
            op_name_lower = op_name.lower()
            
            # Check if it's a describe/get operation
            if any(pattern in op_name_lower for pattern in ['describe', 'get', 'list']):
                # Check if it might be related to our resource type
                if (resource_type.lower() in op_name_lower or 
                    any(pattern in op_name_lower for pattern in self.operation_patterns['resource_patterns'].get(resource_type, []))):
                    operations.append(op_name)
        
        return operations
    
    def call_operation_safely(self, client, operation_name, **kwargs):
        """Safely call an operation with error handling"""
        try:
            operation = getattr(client, operation_name)
            return operation(**kwargs)
        except ClientError as e:
            return {"error": f"ClientError in {operation_name}: {e.response['Error']['Message']}"}
        except Exception as e:
            return {"error": f"Error in {operation_name}: {str(e)}"}
    
    def get_comprehensive_details(self, client, service_name, resource_type, resource_id):
        """Get comprehensive details by trying multiple operations"""
        details = {}
        
        # Try predefined mappings first
        if service_name in self.service_mappings and resource_type in self.service_mappings[service_name]:
            mapping = self.service_mappings[service_name][resource_type]
            operation_name = mapping['operation']
            param_name = mapping['param']
            is_list = mapping['list_param']
            
            # Prepare parameters
            if is_list:
                params = {param_name: [resource_id]}
            else:
                params = {param_name: resource_id}
            
            # Call primary operation
            result = self.call_operation_safely(client, operation_name, **params)
            details['primary'] = result
        
        # Try to discover additional operations
        discovered_ops = self.discover_operations(client, resource_type, resource_id)
        
        for op_name in discovered_ops:
            if op_name == details.get('primary', {}).get('operation'):
                continue  # Skip if we already called this
            
            # Try different parameter combinations
            possible_params = [
                {f"{resource_type.title()}Id": resource_id},
                {f"{resource_type.title()}Name": resource_id},
                {f"{resource_type.title()}Ids": [resource_id]},
                {f"{resource_type.title()}Names": [resource_id]},
                {"Id": resource_id},
                {"Name": resource_id},
                {"Ids": [resource_id]},
                {"Names": [resource_id]}
            ]
            
            for params in possible_params:
                try:
                    result = self.call_operation_safely(client, op_name, **params)
                    if "error" not in result:
                        details[f"additional_{op_name}"] = result
                        break
                except:
                    continue
        
        return details
    
    def _handle_s3(self, client, resource_info):
        """Special handler for S3 buckets"""
        bucket_name = resource_info['id']
        details = {}
        
        # List of S3 operations to try
        s3_operations = [
            ('get_bucket_location', {'Bucket': bucket_name}),
            ('get_bucket_versioning', {'Bucket': bucket_name}),
            ('get_bucket_encryption', {'Bucket': bucket_name}),
            ('get_public_access_block', {'Bucket': bucket_name}),
            ('get_bucket_policy', {'Bucket': bucket_name}),
            ('get_bucket_acl', {'Bucket': bucket_name}),
            ('get_bucket_ownership_controls', {'Bucket': bucket_name}),
            ('get_bucket_notification_configuration', {'Bucket': bucket_name}),
            ('get_bucket_lifecycle_configuration', {'Bucket': bucket_name}),
            ('get_bucket_cors', {'Bucket': bucket_name}),
            ('get_bucket_tagging', {'Bucket': bucket_name}),
            ('get_bucket_logging', {'Bucket': bucket_name}),
            ('get_bucket_website', {'Bucket': bucket_name}),
            ('get_bucket_replication', {'Bucket': bucket_name}),
            ('get_bucket_request_payment', {'Bucket': bucket_name}),
            ('get_bucket_metrics_configuration', {'Bucket': bucket_name}),
            ('get_bucket_inventory_configuration', {'Bucket': bucket_name}),
            ('get_bucket_analytics_configuration', {'Bucket': bucket_name})
        ]
        
        for op_name, params in s3_operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_sns(self, client, resource_info):
        """Special handler for SNS topics"""
        # SNS ARN is already complete
        topic_arn = resource_info['full_resource']
        if not topic_arn.startswith('arn:'):
            # Construct full ARN if needed
            topic_arn = f"arn:aws:sns:{self.region}:{self.session.get_credentials().access_key}:{resource_info['id']}"
        
        details = {}
        sns_operations = [
            ('get_topic_attributes', {'TopicArn': topic_arn}),
            ('list_subscriptions_by_topic', {'TopicArn': topic_arn}),
            ('list_tags_for_resource', {'ResourceArn': topic_arn})
        ]
        
        for op_name, params in sns_operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_sqs(self, client, resource_info):
        """Special handler for SQS queues"""
        queue_name = resource_info['id']
        # Construct queue URL
        queue_url = f"https://sqs.{self.region}.amazonaws.com/{self.session.get_credentials().access_key}/{queue_name}"
        
        details = {}
        sqs_operations = [
            ('get_queue_attributes', {'QueueUrl': queue_url, 'AttributeNames': ['All']}),
            ('list_queue_tags', {'QueueUrl': queue_url})
        ]
        
        for op_name, params in sqs_operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_iam(self, client, resource_info):
        """Special handler for IAM resources"""
        details = {}
        
        if resource_info['type'] == 'role':
            role_name = resource_info['id']
            operations = [
                ('get_role', {'RoleName': role_name}),
                ('list_attached_role_policies', {'RoleName': role_name}),
                ('list_role_policies', {'RoleName': role_name}),
                ('get_role_policy', {'RoleName': role_name}),
            ]
        elif resource_info['type'] == 'user':
            user_name = resource_info['id']
            operations = [
                ('get_user', {'UserName': user_name}),
                ('list_attached_user_policies', {'UserName': user_name}),
                ('list_user_policies', {'UserName': user_name}),
                ('get_groups_for_user', {'UserName': user_name}),
            ]
        elif resource_info['type'] == 'policy':
            policy_arn = f"arn:aws:iam::{self.session.get_credentials().access_key}:policy/{resource_info['id']}"
            operations = [
                ('get_policy', {'PolicyArn': policy_arn}),
                ('list_policy_versions', {'PolicyArn': policy_arn}),
            ]
        else:
            return {"error": f"IAM resource type {resource_info['type']} not supported"}
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_apigateway(self, client, resource_info):
        """Special handler for API Gateway"""
        if resource_info['type'] == 'restapis':
            api_id = resource_info['id'].split('/')[0]  # Get just the API ID
            details = {}
            
            operations = [
                ('get_rest_api', {'restApiId': api_id}),
                ('get_resources', {'restApiId': api_id}),
                ('get_stages', {'restApiId': api_id}),
                ('get_deployments', {'restApiId': api_id}),
            ]
            
            for op_name, params in operations:
                result = self.call_operation_safely(client, op_name, **params)
                details[op_name] = result
            
            return details
        
        return {"error": f"API Gateway resource type {resource_info['type']} not supported"}
    
    # NEW SERVICE HANDLERS
    def _handle_sagemaker(self, client, resource_info):
        """Special handler for SageMaker resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'notebook-instance':
            operations = [
                ('describe_notebook_instance', {'NotebookInstanceName': resource_id}),
                ('list_tags', {'ResourceArn': f"arn:aws:sagemaker:{self.region}:{self.session.get_credentials().access_key}:notebook-instance/{resource_id}"})
            ]
        elif resource_type == 'model':
            operations = [
                ('describe_model', {'ModelName': resource_id}),
                ('list_tags', {'ResourceArn': f"arn:aws:sagemaker:{self.region}:{self.session.get_credentials().access_key}:model/{resource_id}"})
            ]
        elif resource_type == 'endpoint':
            operations = [
                ('describe_endpoint', {'EndpointName': resource_id}),
                ('describe_endpoint_config', {'EndpointConfigName': resource_id}),
                ('list_tags', {'ResourceArn': f"arn:aws:sagemaker:{self.region}:{self.session.get_credentials().access_key}:endpoint/{resource_id}"})
            ]
        elif resource_type == 'training-job':
            operations = [
                ('describe_training_job', {'TrainingJobName': resource_id}),
                ('list_tags', {'ResourceArn': f"arn:aws:sagemaker:{self.region}:{self.session.get_credentials().access_key}:training-job/{resource_id}"})
            ]
        else:
            return {"error": f"SageMaker resource type {resource_type} not supported"}
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_eks(self, client, resource_info):
        """Special handler for EKS clusters"""
        details = {}
        cluster_name = resource_info['id']
        
        operations = [
            ('describe_cluster', {'name': cluster_name}),
            ('list_nodegroups', {'clusterName': cluster_name}),
            ('list_fargate_profiles', {'clusterName': cluster_name}),
            ('describe_addon_versions', {}),
            ('list_addons', {'clusterName': cluster_name})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_ecs(self, client, resource_info):
        """Special handler for ECS resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'cluster':
            operations = [
                ('describe_clusters', {'clusters': [resource_id]}),
                ('list_services', {'cluster': resource_id}),
                ('list_tasks', {'cluster': resource_id}),
                ('list_container_instances', {'cluster': resource_id})
            ]
        elif resource_type == 'service':
            cluster_name = resource_id.split('/')[0] if '/' in resource_id else 'default'
            service_name = resource_id.split('/')[-1]
            operations = [
                ('describe_services', {'cluster': cluster_name, 'services': [service_name]}),
                ('list_tasks', {'cluster': cluster_name, 'serviceName': service_name})
            ]
        elif resource_type == 'task':
            cluster_name = resource_id.split('/')[0] if '/' in resource_id else 'default'
            task_id = resource_id.split('/')[-1]
            operations = [
                ('describe_tasks', {'cluster': cluster_name, 'tasks': [task_id]})
            ]
        else:
            return {"error": f"ECS resource type {resource_type} not supported"}
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_ecr(self, client, resource_info):
        """Special handler for ECR repositories"""
        details = {}
        repo_name = resource_info['id']
        
        operations = [
            ('describe_repositories', {'repositoryNames': [repo_name]}),
            ('describe_images', {'repositoryName': repo_name}),
            ('get_repository_policy', {'repositoryName': repo_name}),
            ('list_tags_for_resource', {'resourceArn': f"arn:aws:ecr:{self.region}:{self.session.get_credentials().access_key}:repository/{repo_name}"})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_athena(self, client, resource_info):
        """Special handler for Athena resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'workgroup':
            operations = [
                ('get_work_group', {'WorkGroup': resource_id}),
                ('list_query_executions', {'WorkGroup': resource_id}),
                ('list_tags_for_resource', {'ResourceARN': f"arn:aws:athena:{self.region}:{self.session.get_credentials().access_key}:workgroup/{resource_id}"})
            ]
        elif resource_type == 'database':
            operations = [
                ('get_database', {'CatalogName': 'AwsDataCatalog', 'DatabaseName': resource_id}),
                ('get_tables', {'CatalogName': 'AwsDataCatalog', 'DatabaseName': resource_id})
            ]
        else:
            return {"error": f"Athena resource type {resource_type} not supported"}
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_glue(self, client, resource_info):
        """Special handler for Glue resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'database':
            operations = [
                ('get_database', {'Name': resource_id}),
                ('get_tables', {'DatabaseName': resource_id}),
                ('get_partitions', {'DatabaseName': resource_id, 'TableName': resource_id})
            ]
        elif resource_type == 'table':
            database_name = resource_id.split('/')[0] if '/' in resource_id else 'default'
            table_name = resource_id.split('/')[-1]
            operations = [
                ('get_table', {'DatabaseName': database_name, 'Name': table_name}),
                ('get_partitions', {'DatabaseName': database_name, 'TableName': table_name})
            ]
        elif resource_type == 'crawler':
            operations = [
                ('get_crawler', {'Name': resource_id}),
                ('get_crawler_metrics', {'CrawlerNameList': [resource_id]})
            ]
        elif resource_type == 'job':
            operations = [
                ('get_job', {'JobName': resource_id}),
                ('get_job_runs', {'JobName': resource_id}),
                ('list_tags_for_resource', {'ResourceArn': f"arn:aws:glue:{self.region}:{self.session.get_credentials().access_key}:job/{resource_id}"})
            ]
        else:
            return {"error": f"Glue resource type {resource_type} not supported"}
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_emr(self, client, resource_info):
        """Special handler for EMR clusters"""
        details = {}
        cluster_id = resource_info['id']
        
        operations = [
            ('describe_cluster', {'ClusterId': cluster_id}),
            ('list_steps', {'ClusterId': cluster_id}),
            ('list_instance_groups', {'ClusterId': cluster_id}),
            ('describe_security_configuration', {'Name': cluster_id})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_elasticbeanstalk(self, client, resource_info):
        """Special handler for Elastic Beanstalk resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'application':
            operations = [
                ('describe_applications', {'ApplicationNames': [resource_id]}),
                ('describe_application_versions', {'ApplicationName': resource_id}),
                ('describe_environments', {'ApplicationName': resource_id})
            ]
        elif resource_type == 'environment':
            operations = [
                ('describe_environments', {'EnvironmentNames': [resource_id]}),
                ('describe_environment_health', {'EnvironmentName': resource_id}),
                ('describe_environment_resources', {'EnvironmentName': resource_id}),
                ('describe_events', {'EnvironmentName': resource_id})
            ]
        else:
            return {"error": f"Elastic Beanstalk resource type {resource_type} not supported"}
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_appsync(self, client, resource_info):
        """Special handler for AppSync GraphQL APIs"""
        details = {}
        api_id = resource_info['id']
        
        operations = [
            ('get_graphql_api', {'apiId': api_id}),
            ('list_data_sources', {'apiId': api_id}),
            ('list_resolvers', {'apiId': api_id, 'typeName': 'Query'}),
            ('list_functions', {'apiId': api_id}),
            ('list_tags_for_resource', {'resourceArn': f"arn:aws:appsync:{self.region}:{self.session.get_credentials().access_key}:apis/{api_id}"})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_stepfunctions(self, client, resource_info):
        """Special handler for Step Functions state machines"""
        details = {}
        state_machine_arn = resource_info['full_resource']
        if not state_machine_arn.startswith('arn:'):
            state_machine_arn = f"arn:aws:states:{self.region}:{self.session.get_credentials().access_key}:stateMachine:{resource_info['id']}"
        
        operations = [
            ('describe_state_machine', {'stateMachineArn': state_machine_arn}),
            ('list_executions', {'stateMachineArn': state_machine_arn}),
            ('list_tags_for_resource', {'resourceArn': state_machine_arn})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_events(self, client, resource_info):
        """Special handler for EventBridge/CloudWatch Events"""
        details = {}
        rule_name = resource_info['id']
        
        operations = [
            ('describe_rule', {'Name': rule_name}),
            ('list_targets_by_rule', {'Rule': rule_name}),
            ('list_tags_for_resource', {'ResourceARN': f"arn:aws:events:{self.region}:{self.session.get_credentials().access_key}:rule/{rule_name}"})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_guardduty(self, client, resource_info):
        """Special handler for GuardDuty detectors"""
        details = {}
        detector_id = resource_info['id']
        
        operations = [
            ('get_detector', {'DetectorId': detector_id}),
            ('list_findings', {'DetectorId': detector_id}),
            ('list_members', {'DetectorId': detector_id}),
            ('list_threat_intel_sets', {'DetectorId': detector_id}),
            ('list_ip_sets', {'DetectorId': detector_id})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_macie(self, client, resource_info):
        """Special handler for Macie resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'classification-job':
            operations = [
                ('describe_classification_job', {'jobId': resource_id}),
                ('list_findings', {'findingCriteria': {'criterion': {'type': {'eq': ['Policy:IAMUser/S3BucketPublic']}}}})
            ]
        else:
            operations = [
                ('get_macie_session', {}),
                ('get_usage_statistics', {}),
                ('list_classification_jobs', {})
            ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_inspector(self, client, resource_info):
        """Special handler for Inspector resources"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'assessment-template':
            operations = [
                ('describe_assessment_templates', {'assessmentTemplateArns': [resource_id]}),
                ('describe_assessment_runs', {'assessmentTemplateArns': [resource_id]}),
                ('list_tags_for_resource', {'resourceArn': resource_id})
            ]
        else:
            operations = [
                ('describe_assessment_targets', {}),
                ('describe_rules_packages', {}),
                ('list_assessment_runs', {})
            ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_securityhub(self, client, resource_info):
        """Special handler for Security Hub"""
        details = {}
        
        operations = [
            ('get_enabled_standards', {}),
            ('get_findings', {}),
            ('get_insights', {}),
            ('describe_hub', {}),
            ('list_members', {})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_config(self, client, resource_info):
        """Special handler for AWS Config"""
        details = {}
        resource_type = resource_info['type']
        resource_id = resource_info['id']
        
        if resource_type == 'configuration-recorder':
            operations = [
                ('describe_configuration_recorders', {'ConfigurationRecorderNames': [resource_id]}),
                ('describe_configuration_recorder_status', {'ConfigurationRecorderNames': [resource_id]}),
                ('describe_delivery_channels', {})
            ]
        else:
            operations = [
                ('describe_configuration_recorders', {}),
                ('describe_delivery_channels', {}),
                ('get_compliance_summary_by_config_rule', {}),
                ('describe_config_rules', {})
            ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_budgets(self, client, resource_info):
        """Special handler for AWS Budgets"""
        details = {}
        budget_name = resource_info['id']
        account_id = self.session.get_credentials().access_key
        
        operations = [
            ('describe_budget', {'AccountId': account_id, 'BudgetName': budget_name}),
            ('describe_budget_performance_history', {'AccountId': account_id, 'BudgetName': budget_name}),
            ('describe_notifications_for_budget', {'AccountId': account_id, 'BudgetName': budget_name}),
            ('describe_subscribers_for_notification', {'AccountId': account_id, 'BudgetName': budget_name})
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def _handle_cost_explorer(self, client, resource_info):
        """Special handler for Cost Explorer"""
        details = {}
        
        operations = [
            ('get_cost_and_usage', {
                'TimePeriod': {
                    'Start': '2023-01-01',
                    'End': '2023-12-31'
                },
                'Granularity': 'MONTHLY',
                'Metrics': ['BlendedCost']
            }),
            ('get_usage_forecast', {
                'TimePeriod': {
                    'Start': '2023-01-01',
                    'End': '2023-12-31'
                },
                'Granularity': 'MONTHLY',
                'Metric': 'BLENDED_COST'
            }),
            ('get_dimension_values', {
                'TimePeriod': {
                    'Start': '2023-01-01',
                    'End': '2023-12-31'
                },
                'Dimension': 'SERVICE'
            })
        ]
        
        for op_name, params in operations:
            result = self.call_operation_safely(client, op_name, **params)
            details[op_name] = result
        
        return details
    
    def get_resource_details(self, arn):
        """Main method to get resource details dynamically"""
        try:
            # Parse ARN
            arn_info = self.parse_arn(arn)
            if not arn_info:
                return {"error": "Invalid ARN format"}
            
            service_name = arn_info['service']
            region = arn_info['region'] or self.region
            
            # Extract resource information
            resource_info = self.extract_resource_info(arn_info['resource'])
            
            # Get appropriate client
            client = self.get_client(service_name, region)
            
            # Use special handler if available
            if service_name in self.special_handlers:
                details = self.special_handlers[service_name](client, resource_info)
            else:
                # Use generic approach
                details = self.get_comprehensive_details(client, service_name, resource_info['type'], resource_info['id'])
            
            return {
                "arn": arn,
                "service": service_name,
                "region": region,
                "resource_type": resource_info['type'],
                "resource_id": resource_info['id'],
                "details": details
            }
            
        except Exception as e:
            return {"error": f"Failed to get resource details: {str(e)}"}


# def generate_terraform_from_resource_details(arn, inspector):
#     resource_info = inspector.get_resource_details(arn)

#     if "error" in resource_info:
#         return f"❌ Error fetching resource: {resource_info['error']}"

#     service = resource_info.get("service")
#     resource_type = resource_info.get("resource_type")
#     resource_id = resource_info.get("resource_id")
#     config_details = resource_info.get("details")

#     # prompt = f"""
#     # You are an expert Terraform engineer.

#     # Generate production-ready Terraform HCL code that exactly represents the live AWS resource configuration.Terraform code should be generated based on the configurations provided.

#     # ### Instructions:
#     # - Use the same resource name: `{resource_id}`
#     # - Do NOT add any defaults that are not present in the config.
#     # - Assume default provider (no need to add credentials).
#     # - ONLY use the values and properties that exist in the actual config.
#     # - See the configurations provided and generate the code accordingly.
#     # - Give much more weightage to the configurations fetched , because the service is already created and we are just generating the code for it.
#     # - Do not add anything new to the code, just generate the code as it is there in existing format.
#     # - Do not add any type of explanation to the code, just generate the code.
#     # - Do not add any type of comments to the code, just generate the code.
#     # - Do NOT include provider block or outputs.
#     # - Generate only pure Terraform code based on the provided configuration.

#     # ### Resource metadata:
#     # Service: {service}
#     # Type: {resource_type}
#     # Region: {resource_info.get('region')}
#     # Resource ID: {resource_id}

#     # ### Configuration:
#     # {json.dumps(config_details, indent=2, default=str)}

#     # Now generate complete and correct Terraform HCL code below:
#     # """
#     prompt = f"""
#     You are an expert Terraform engineer.

#     Generate production-ready Terraform HCL code that exactly represents the live AWS resource configuration.

#     ### Requirements:
#     - Use the resource name `{resource_id}`.
#     - Do NOT add any defaults that are not present in the config.
#     - Do NOT explain anything.
#     - Do NOT include comments.
#     - ONLY use the values and properties that exist in the actual config.
#     - Do NOT include provider block or outputs.
#     - Do NOT include any depricated properties into terraform code.
#     - Do NOT include any `acl` block or `aws_s3_bucket_acl` resource if the bucket uses `BucketOwnerEnforced` ownership (ACLs are disabled in that case).
#     - Generate only pure Terraform code based on the provided configuration.

#     ### AWS Resource Metadata:
#     Service: {service}
#     Type: {resource_type}
#     Region: {resource_info.get('region')}
#     Resource ID: {resource_id}

#     ### Actual Configuration (in JSON):
#     {json.dumps(config_details, indent=2, default=str)}

#     Now generate only the corresponding Terraform HCL code:
#     """

#     try:
#         response = client.chat.completions.create(
#             model="gpt-4o",
#             messages=[
#                 {"role": "system", "content": "You are a DevOps expert who writes Terraform."},
#                 {"role": "user", "content": prompt}
#             ],
#             temperature=0.4,
#             max_tokens=1500
#         )
#         return response.choices[0].message.content
#     except Exception as e:
#         return f"❌ OpenAI API call failed: {str(e)}"



def remove_invalid_volume_ids(config: dict) -> dict:
    """
    Recursively remove volume_id entries from root_block_device or ebs_block_device
    where the volume might no longer exist.
    """
    def clean_block(block):
        if isinstance(block, list):
            return [clean_block(b) for b in block]
        elif isinstance(block, dict):
            block.pop("volume_id", None)
            return {k: clean_block(v) for k, v in block.items()}
        return block

    if "primary" in config:
        resource = config["primary"]
        if isinstance(resource, dict):
            for key in ["BlockDeviceMappings", "RootBlockDevice"]:
                if key in resource:
                    config["primary"][key] = clean_block(resource[key])

    return config






def generate_terraform_from_resource_details(arns: list[str], inspector: DynamicAWSResourceInspector) -> str:
    all_code_blocks = []

    for arn in arns:
        resource_info = inspector.get_resource_details(arn)

        if "error" in resource_info:
            print(f"❌ Error fetching resource: {resource_info['error']}")
            continue

        service = resource_info.get("service")
        resource_type = resource_info.get("resource_type")
        resource_id = resource_info.get("resource_id")
        #config_details = resource_info.get("details")

        config_details = remove_invalid_volume_ids(resource_info.get("details"))


        prompt = f"""
        You are an expert Terraform DevOps engineer.

        Generate production-ready **Terraform HCL code** that matches the live AWS resource configuration provided below.

        ---

        ### 🔒 STRICT INSTRUCTIONS:
        - Only generate a single valid Terraform `resource` block for the AWS resource.
        - Do **NOT** include:
        - provider blocks
        - outputs
        - data blocks
        - locals
        - variable declarations
        - modules
        - comments
        - explanations
        - Do **NOT** add default values unless they are explicitly present in the input.
        - Do **NOT** guess or infer missing fields.
        - Do **NOT** include any deprecated or legacy Terraform attributes.
        - Do **NOT** include `acl` or `aws_s3_bucket_acl` if the bucket has `BucketOwnerEnforced` ownership.
        - Use the exact resource name `{resource_id}`.
        - All values must come strictly from the actual configuration JSON.

        ---

        ### 📦 AWS Resource Metadata:
        Service: {service}  
        Type: {resource_type}  
        Region: {resource_info.get('region')}  
        Resource ID: {resource_id}  

        ---

        ### 🔧 Actual Live Configuration (in JSON):
        {json.dumps(config_details, indent=2, default=str)}

        ---

        Now generate the exact Terraform HCL code for this resource only (no extras):
        """.strip()

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a DevOps expert who writes Terraform."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=15000
            )
            tf_code = response.choices[0].message.content
            cleaned_code = clean_terraform_code(tf_code)
            all_code_blocks.append(cleaned_code)

        except Exception as e:
            print(f"❌ OpenAI API call failed for {arn}: {str(e)}")
            continue

    return "\n\n".join(all_code_blocks)


def get_aws_resource_type_from_arn(arn: str) -> str:
        """
        Detects the corresponding Terraform resource type from a given AWS ARN.

        Returns:
            str: Terraform resource type (e.g., 'aws_instance'), or None if unknown.
        """
        parts = arn.split(':')
        if len(parts) < 6:
            return None

        service = parts[2]
        resource_part = parts[5]

        # Basic mapping from AWS service to Terraform resource type
        service_to_tf = {
            's3': 'aws_s3_bucket',
            'ec2': 'aws_instance',
            'rds': 'aws_db_instance',
            'lambda': 'aws_lambda_function',
            'dynamodb': 'aws_dynamodb_table',
            'sns': 'aws_sns_topic',
            'sqs': 'aws_sqs_queue',
            'iam': {
                'user': 'aws_iam_user',
                'role': 'aws_iam_role',
                'policy': 'aws_iam_policy',
                'group': 'aws_iam_group'
            },
            'cloudfront': 'aws_cloudfront_distribution',
            'apigateway': 'aws_api_gateway_rest_api',
            'logs': 'aws_cloudwatch_log_group',
            'cloudwatch': 'aws_cloudwatch_metric_alarm',
            'autoscaling': 'aws_autoscaling_group',
            'kms': 'aws_kms_key',
            'elasticloadbalancing': 'aws_elb',
            'elasticloadbalancingv2': 'aws_lb',
            'route53': 'aws_route53_zone',
            'secretsmanager': 'aws_secretsmanager_secret',
            'ssm': 'aws_ssm_parameter',
            'config': 'aws_config_configuration_recorder',
            'codebuild': 'aws_codebuild_project',
            'ecr': 'aws_ecr_repository',
            'ecs': 'aws_ecs_cluster',
            'eks': 'aws_eks_cluster',
            'sagemaker': 'aws_sagemaker_notebook_instance',
            'cloudformation': 'aws_cloudformation_stack',
            'cloudfront': 'aws_cloudfront_distribution',
            'cloudwatch': 'aws_cloudwatch_metric_alarm',
            'cloudwatchlogs': {
                'log-group': 'aws_cloudwatch_log_group',
                'log-stream': 'aws_cloudwatch_log_stream',
                'subscription': 'aws_cloudwatch_log_subscription',
                'subscription-filter': 'aws_cloudwatch_log_subscription_filter'}
                }

        # Handle IAM specifically
        if service == 'iam':
            # IAM ARNs look like: arn:aws:iam::123456789012:user/JohnDoe
            if '/' in resource_part:
                iam_type = resource_part.split('/')[0]
                return service_to_tf['iam'].get(iam_type)

        # Standard services
        if service in service_to_tf:
            return service_to_tf[service]

        # Fallback: infer from resource type prefix
        if '/' in resource_part:
            inferred_type = resource_part.split('/')[0]
        elif ':' in resource_part:
            inferred_type = resource_part.split(':')[0]
        else:
            inferred_type = resource_part
        
        fallback_mapping = {
            # EC2
            'instance': 'aws_instance',
            'volume': 'aws_ebs_volume',
            'vpc': 'aws_vpc',
            'subnet': 'aws_subnet',
            'security-group': 'aws_security_group',
            'key-pair': 'aws_key_pair',
            'image': 'aws_ami',
            'snapshot': 'aws_ebs_snapshot',
            'network-interface': 'aws_network_interface',
            'route-table': 'aws_route_table',
            'internet-gateway': 'aws_internet_gateway',

            #S3 bucket
            'bucket': 'aws_s3_bucket',

            # RDS
            'db': 'aws_db_instance',
            'cluster': 'aws_rds_cluster',
            'db-cluster': 'aws_rds_cluster',
            'db-instance': 'aws_db_instance',
            'db-snapshot': 'aws_db_snapshot',

            # Lambda
            'function': 'aws_lambda_function',

            # IAM
            'role': 'aws_iam_role',
            'user': 'aws_iam_user',
            'policy': 'aws_iam_policy',

            # DynamoDB
            'table': 'aws_dynamodb_table',

            # SNS / SQS
            'topic': 'aws_sns_topic',
            'queue': 'aws_sqs_queue',

            # CloudFormation
            'stack': 'aws_cloudformation_stack',

            # CloudWatch
            'alarm': 'aws_cloudwatch_metric_alarm',

            # Logs
            'log-group': 'aws_cloudwatch_log_group',

            # SecretsManager / SSM / KMS
            'secret': 'aws_secretsmanager_secret',
            'parameter': 'aws_ssm_parameter',
            'key': 'aws_kms_key',

            # API Gateway
            'restapis': 'aws_api_gateway_rest_api',
            'rest-api': 'aws_api_gateway_rest_api',

            # CloudFront / EFS / Elasticache / Redshift
            'distribution': 'aws_cloudfront_distribution',
            'file-system': 'aws_efs_file_system',
            'cluster': 'aws_elasticache_cluster',  # also used for redshift and emr
            'cache-cluster': 'aws_elasticache_cluster',
            'redshift-cluster': 'aws_redshift_cluster',

            # Auto Scaling
            'autoScalingGroup': 'aws_autoscaling_group',

            # Route53
            'hostedzone': 'aws_route53_zone',

            # ELB
            'loadbalancer': 'aws_elb',  # classic
            'targetgroup': 'aws_lb_target_group',  # used in elbv2

            # SageMaker
            'notebook-instance': 'aws_sagemaker_notebook_instance',
            'model': 'aws_sagemaker_model',
            'endpoint': 'aws_sagemaker_endpoint',
            'endpoint-config': 'aws_sagemaker_endpoint_configuration',
            'training-job': 'aws_sagemaker_training_job',

            # EKS / ECS / ECR
            'eks-cluster': 'aws_eks_cluster',
            'nodegroup': 'aws_eks_node_group',
            'ecs-cluster': 'aws_ecs_cluster',
            'service': 'aws_ecs_service',
            'task': 'aws_ecs_task',
            'repository': 'aws_ecr_repository',

            # Athena / Glue
            'workgroup': 'aws_athena_workgroup',
            'glue-database': 'aws_glue_catalog_database',
            'glue-table': 'aws_glue_catalog_table',
            'crawler': 'aws_glue_crawler',
            'job': 'aws_glue_job',

            # EMR
            'emr-cluster': 'aws_emr_cluster',

            # Beanstalk
            'application': 'aws_elastic_beanstalk_application',
            'environment': 'aws_elastic_beanstalk_environment',

            # AppSync
            'graphqlApi': 'aws_appsync_graphql_api',

            # Step Functions
            'stateMachine': 'aws_sfn_state_machine',

            # EventBridge
            'rule': 'aws_cloudwatch_event_rule',

            # GuardDuty / Macie / Inspector / SecurityHub
            'detector': 'aws_guardduty_detector',
            'classification-job': 'aws_macie2_classification_job',
            'assessment-template': 'aws_inspector_assessment_template',
            'hub': 'aws_securityhub_hub',

            # AWS Config
            'configuration-recorder': 'aws_config_configuration_recorder',

            # Budgets
            'budget': 'aws_budgets_budget',

            # Cost Explorer (not importable but listable)
            'cost-and-usage': 'aws_ce_cost_category'
        }
        return fallback_mapping.get(inferred_type)


def run_terraform_import_for_arn(main_tf_path: str, arn: str) -> str:
    """
    Initializes Terraform and runs `terraform import` using the given ARN.
    Detects the resource type from the ARN, and finds the primary resource name from main.tf.
    """
    if not os.path.exists(main_tf_path):
        return "❌ main.tf file not found."

    with open(main_tf_path, "r") as f:
        tf_content = f.read()

    resource_type = get_aws_resource_type_from_arn(arn)
    if not resource_type:
        return "❌ Could not determine AWS resource type from ARN."

    # Find resource name for the detected type in main.tf (first match = primary)
    pattern = re.compile(r'resource\s+"{}"\s+"([\w\-]+)"\s*\{{'.format(re.escape(resource_type)))
    match = pattern.search(tf_content)
    if not match:
        return f"❌ Could not find a resource block of type {resource_type} in main.tf"

    resource_name = match.group(1)
    print(f"📦 Detected Terraform resource: {resource_type}.{resource_name}")

    working_dir = os.path.dirname(os.path.abspath(main_tf_path)) or os.getcwd()
    terraform_tfstate_path = os.path.join(working_dir, "terraform.tfstate")

    try:
        print("🔧 Running `terraform init`...")
        subprocess.run(["terraform", "init"], cwd=working_dir, check=True)

        print(f"📥 Importing resource with ARN/ID: {arn}")
        import_id = get_import_id(resource_type, arn)
        print(f"🔍 Import ID: {import_id}")

        subprocess.run(
            ["terraform", "import", f"{resource_type}.{resource_name}", import_id],
            cwd=working_dir,
            check=True
            )


        if os.path.exists(terraform_tfstate_path):
            print(f"✅ Terraform state file created at: {terraform_tfstate_path}")
        else:
            return "⚠️ Terraform import succeeded but .tfstate file not found."

        return f"""✅ Terraform Import Successful for `{resource_type}.{resource_name}` 
                📄 State saved at: `{terraform_tfstate_path}`"""

    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode() if hasattr(e.stderr, 'decode') else str(e)
        return f"❌ Error running Terraform commands:\n{stderr}"



def get_import_id(resource_type: str, arn: str) -> str:
    """
    Determines the correct import ID for a Terraform resource based on its type and ARN.

    Terraform requires a specific ID format for the `import` command, which often
    differs from the full resource ARN. This function contains a mapping of
    resource types to functions that extract the correct ID.

    Args:
        resource_type (str): The Terraform resource type (e.g., 'aws_instance').
        arn (str): The full AWS ARN of the resource.

    Returns:
        str: The calculated import ID suitable for the `terraform import` command.
             Returns the full ARN as a fallback if the type is not recognized.
    """
    if not resource_type:
        # Fallback if resource type couldn't be determined
        return arn

    # A dictionary mapping Terraform resource types to a lambda function
    # that extracts the correct import ID from the ARN parts.
    ARN_IMPORT_ID_EXTRACTORS = {
        # --- EC2 ---
        'aws_instance': lambda parts, res: res.split('/')[-1],
        'aws_vpc': lambda parts, res: res.split('/')[-1],
        'aws_subnet': lambda parts, res: res.split('/')[-1],
        'aws_security_group': lambda parts, res: res.split('/')[-1],
        'aws_route_table': lambda parts, res: res.split('/')[-1],
        'aws_internet_gateway': lambda parts, res: res.split('/')[-1],
        'aws_key_pair': lambda parts, res: res.split('/')[-1],
        'aws_ebs_volume': lambda parts, res: res.split('/')[-1],
        'aws_ebs_snapshot': lambda parts, res: res.split('/')[-1],
        'aws_network_interface': lambda parts, res: res.split('/')[-1],
        'aws_ami': lambda parts, res: res.split('/')[-1],

        # --- S3 ---
        'aws_s3_bucket': lambda parts, res: res, # The resource part is the bucket name

        # --- IAM ---
        'aws_iam_role': lambda parts, res: res.split('/')[-1],
        'aws_iam_user': lambda parts, res: res.split('/')[-1],
        'aws_iam_group': lambda parts, res: res.split('/')[-1],
        'aws_iam_policy': lambda parts, res: ':'.join(parts), # Requires full ARN

        # --- Lambda, RDS, DynamoDB ---
        'aws_lambda_function': lambda parts, res: res,
        'aws_rds_cluster': lambda parts, res: res.split(':')[-1],
        'aws_db_instance': lambda parts, res: res.split(':')[-1],
        'aws_dynamodb_table': lambda parts, res: res.split('/')[-1],

        # --- Networking & Content Delivery ---
        'aws_route53_zone': lambda parts, res: res.split('/')[-1],
        'aws_cloudfront_distribution': lambda parts, res: res.split('/')[-1],
        'aws_elb': lambda parts, res: res.split('/')[-1], # Classic ELB
        'aws_lb': lambda parts, res: ':'.join(parts), # v2 Load Balancers (ALB/NLB) use ARN
        'aws_lb_target_group': lambda parts, res: ':'.join(parts), # Target Groups use ARN

        # --- Containers (ECS, ECR, EKS) ---
        'aws_ecr_repository': lambda parts, res: res.split('/')[-1],
        'aws_ecs_cluster': lambda parts, res: res.split('/')[-1],
        'aws_ecs_service': lambda parts, res: res, # Import ID is "cluster_name/service_name"
        'aws_eks_cluster': lambda parts, res: res.split('/')[-1],

        # --- Storage & Databases ---
        'aws_efs_file_system': lambda parts, res: res.split('/')[-1],
        'aws_elasticache_cluster': lambda parts, res: res.split(':')[-1],
        'aws_redshift_cluster': lambda parts, res: res.split(':')[-1],

        # --- Management & Governance ---
        'aws_cloudformation_stack': lambda parts, res: res.split('/')[1],
        'aws_cloudwatch_log_group': lambda parts, res: res.split(':')[-1],
        'aws_cloudwatch_metric_alarm': lambda parts, res: res.split(':')[-1],
        'aws_autoscaling_group': lambda parts, res: res.split(':')[-1].split('/')[-1],
        'aws_config_configuration_recorder': lambda parts, res: res.split('/')[-1],
        'aws_budgets_budget': lambda parts, res: f"{parts[4]}:{res.split(':')[-1]}", # "account_id:budget_name"

        # --- Security, Identity, & Compliance ---
        'aws_kms_key': lambda parts, res: res.split('/')[-1],
        'aws_secretsmanager_secret': lambda parts, res: ':'.join(parts), # Uses ARN
        'aws_guardduty_detector': lambda parts, res: res.split('/')[-1],
        'aws_inspector_assessment_template': lambda parts, res: ':'.join(parts), # Uses ARN
        'aws_securityhub_hub': lambda parts, res: res.split('/')[-1],
        'aws_macie2_classification_job': lambda parts, res: res.split('/')[-1],

        # --- Analytics ---
        'aws_glue_crawler': lambda parts, res: res.split('/')[-1],
        'aws_glue_job': lambda parts, res: res.split('/')[-1],
        'aws_athena_workgroup': lambda parts, res: res.split('/')[-1],
        'aws_emr_cluster': lambda parts, res: res.split('/')[-1],

        # --- Application Integration ---
        'aws_sqs_queue': lambda parts, res: res, # The resource part is the queue name
        'aws_sns_topic': lambda parts, res: ':'.join(parts), # Uses ARN
        'aws_stepfunctions_state_machine': lambda parts, res: ':'.join(parts), # Uses ARN
        'aws_apigateway_rest_api': lambda parts, res: res.split('/')[-1],
        'aws_appsync_graphql_api': lambda parts, res: res.split('/')[-1],
        'aws_cloudwatch_event_rule': lambda parts, res: res.split('/')[-1],

        # --- Developer Tools & Beanstalk ---
        'aws_elastic_beanstalk_application': lambda parts, res: res,
        'aws_elastic_beanstalk_environment': lambda parts, res: res,
    }

    # Split the ARN into its components
    parts = arn.split(':')
    if len(parts) < 6:
        return arn  # Return the original string if it's not a valid ARN

    resource_part = parts[5]

    # Find the extractor function for the given resource type
    extractor = ARN_IMPORT_ID_EXTRACTORS.get(resource_type)

    if extractor:
        return extractor(parts, resource_part)
    else:
        # As a safe default, return the full ARN. Some resources use it, and
        # for others, it will provide a clear error message during import.
        print(f"⚠️ Warning: No specific import ID rule for '{resource_type}'. Defaulting to full ARN.")
        return arn



def clean_terraform_code(raw_code: str) -> str:
    """
    Cleans Terraform code:
    - Removes ```hcl or ``` markers
    """
    lines = raw_code.splitlines()

    cleaned_lines = [
        line for line in lines if not line.strip().startswith("```")
    ]

    return "\n".join(cleaned_lines).strip()


# def import_and_apply_for_resource(main_tf_path: str, arn: str) -> str:
#     """
#     Loads an existing .tfstate file (if available), runs `terraform import`, then `terraform apply`.
#     """

#     working_dir = os.path.dirname(os.path.abspath(main_tf_path)) or os.getcwd()
#     terraform_tfstate_path = os.path.join(working_dir, "terraform.tfstate")

#     # Read resource type and name from main.tf
#     with open(main_tf_path, "r") as f:
#         tf_content = f.read()

#     # Try to detect resource block
#     match = re.search(r'resource\s+"([\w_]+)"\s+"([\w\-]+)"\s*{', tf_content)
#     if not match:
#         return "❌ Could not detect a resource block in main.tf"

#     resource_type, resource_name = match.group(1), match.group(2)
#     print(f"📦 Found resource: {resource_type}.{resource_name}")

#     # Determine proper import ID
#     import_id = get_import_id(resource_type, arn)
#     print(f"📥 Importing with ID: {import_id}")

#     try:
#         # Run terraform init
#         print("🔨 Running terraform init...")
#         subprocess.run(["terraform", "init"], cwd=working_dir, check=True)

#         # Run terraform import
#         print(f"📥 Running terraform import...")
#         subprocess.run(
#             ["terraform", "import", f"{resource_type}.{resource_name}", import_id],
#             cwd=working_dir,
#             check=True
#         )

#         # Run terraform apply
#         print("🚀 Running terraform apply...")
#         result = subprocess.run(
#             ["terraform", "apply", "-auto-approve"],
#             cwd=working_dir,
#             capture_output=True,
#             text=True
#         )

#         # Success check
#         if result.returncode == 0:
#             return f"""✅ Terraform Import & Apply Successful for `{resource_type}.{resource_name}`
# 📄 State file: `{terraform_tfstate_path}`

# ```bash
# {result.stdout}
# ```"""
#         else:
#             return f"""❌ Terraform Apply Failed
# ```bash
# {result.stderr}
# ```"""

#     except subprocess.CalledProcessError as e:
#         return f"❌ Terraform Command Error:\n{e.stderr or str(e)}"



# def import_and_apply_for_resource(main_tf_path: str, arns: list[str]) -> str:
#     """
#     Imports each resource from ARNs into Terraform state and applies the configuration.
#     """
#     logs = []
#     working_dir = os.path.dirname(os.path.abspath(main_tf_path)) or os.getcwd()
#     terraform_tfstate_path = os.path.join(working_dir, "terraform.tfstate")

#     if not os.path.exists(main_tf_path):
#         return "❌ main.tf file not found."

#     with open(main_tf_path, "r") as f:
#         tf_content = f.read()

#     # Run terraform init once
#     try:
#         logs.append("🔨 Running terraform init...")
#         subprocess.run(["terraform", "init"], cwd=working_dir, check=True)
#     except subprocess.CalledProcessError as e:
#         logs.append(f"❌ Terraform init failed:\n{e.stderr or str(e)}")
#         return "\n".join(logs)

#     # Process each ARN separately
#     for arn in arns:
#         resource_type = get_aws_resource_type_from_arn(arn)
#         import_id = get_import_id(resource_type, arn)

#         # Dynamically find the matching resource name
#         pattern = re.compile(rf'resource\s+"{resource_type}"\s+"([\w\-]+)"\s*{{')
#         match = pattern.search(tf_content)
#         if not match:
#             logs.append(f"❌ Could not find Terraform resource for type: {resource_type} (ARN: {arn})")
#             continue

#         resource_name = match.group(1)
#         logs.append(f"📦 Importing `{resource_type}.{resource_name}` with ID: {import_id}")

#         try:
#             subprocess.run(
#                 ["terraform", "import", f"{resource_type}.{resource_name}", import_id],
#                 cwd=working_dir,
#                 check=True,
#                 capture_output=True,
#                 text=True
#             )
#             logs.append(f"✅ Import successful for {resource_type}.{resource_name}")
#         except subprocess.CalledProcessError as e:
#             logs.append(f"❌ Import failed for {resource_type}.{resource_name}\n{e.stderr or str(e)}")

#     # Run terraform apply once after all imports
#     try:
#         logs.append("🚀 Running terraform apply...")
#         apply_proc = subprocess.run(
#             ["terraform", "apply", "-auto-approve"],
#             cwd=working_dir,
#             capture_output=True,
#             text=True
#         )

#         if apply_proc.returncode == 0:
#             logs.append("✅ Terraform Apply Successful")
#             logs.append(f"```bash\n{apply_proc.stdout}\n```")
#         else:
#             logs.append("❌ Terraform Apply Failed")
#             logs.append(f"```bash\n{apply_proc.stderr}\n```")

#     except subprocess.CalledProcessError as e:
#         logs.append(f"❌ Terraform apply error:\n{e.stderr or str(e)}")

#     return "\n".join(logs)

def import_and_apply_for_resource(main_tf_path: str, arns: list[str], user_id: int, project_name: str) -> str:
    """
    Imports each resource from ARNs into Terraform state, applies the configuration,
    and updates workspace status in the DB if apply is successful.
    """

    logs = []
    working_dir = os.path.dirname(os.path.abspath(main_tf_path)) or os.getcwd()
    terraform_tfstate_path = os.path.join(working_dir, "terraform.tfstate")

    if not os.path.exists(main_tf_path):
        return "❌ main.tf file not found."

    with open(main_tf_path, "r") as f:
        tf_content = f.read()

    # Run terraform init once
    try:
        logs.append("🔨 Running terraform init...")
        subprocess.run(["terraform", "init"], cwd=working_dir, check=True)
    except subprocess.CalledProcessError as e:
        logs.append(f"❌ Terraform init failed:\n{e.stderr or str(e)}")
        return "\n".join(logs)

    # Process each ARN separately
    for arn in arns:
        resource_type = get_aws_resource_type_from_arn(arn)
        import_id = get_import_id(resource_type, arn)

        pattern = re.compile(rf'resource\s+"{resource_type}"\s+"([\w\-]+)"\s*{{')
        match = pattern.search(tf_content)
        if not match:
            logs.append(f"❌ Could not find Terraform resource for type: {resource_type} (ARN: {arn})")
            continue

        resource_name = match.group(1)
        logs.append(f"📦 Importing `{resource_type}.{resource_name}` with ID: {import_id}")

        try:
            subprocess.run(
                ["terraform", "import", f"{resource_type}.{resource_name}", import_id],
                cwd=working_dir,
                check=True,
                capture_output=True,
                text=True
            )
            logs.append(f"✅ Import successful for {resource_type}.{resource_name}")
        except subprocess.CalledProcessError as e:
            logs.append(f"❌ Import failed for {resource_type}.{resource_name}\n{e.stderr or str(e)}")

    # Apply Terraform
    try:
        logs.append("🚀 Running terraform apply...")
        apply_proc = subprocess.run(
            ["terraform", "apply", "-auto-approve"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )

        if apply_proc.returncode == 0:
            logs.append("✅ Terraform Apply Successful")
            logs.append(f"```bash\n{apply_proc.stdout}\n```")

            # ✅ Update DB status only on success
            try:
                with get_db_session() as db:
                    status_payload = WorkspaceStatusCreate(
                        userid=user_id,
                        project_name=project_name,
                        status=apply_proc.stdout.strip()
                    )
                    print("📝 Updating workspace status...")
                    assert create_or_update_workspace_status(db=db, status_data=status_payload)
                    print("✅ Workspace status updated.")

                    minio_file_path = f"{project_name}_terraform/main.tf"
                    # Update Workspace (filelocation to MinIO path)
            
                    workspace_payload = WorkspaceCreate(
                            userid=user_id,
                            wsname=project_name,
                            filetype="terraform",
                            filelocation=minio_file_path,
                            diagramjson=None
                        )
                    print("📁 Updating workspace record...")
                    assert create_or_update_workspace(db=db, workspace_data=workspace_payload)
                    print("✅ Workspace table updated.")
            except Exception as db_err:
                logs.append(f"❌ Failed to update workspace status: {str(db_err)}")

        else:
            logs.append("❌ Terraform Apply Failed")
            logs.append(f"```bash\n{apply_proc.stderr}\n```")

    except subprocess.CalledProcessError as e:
        logs.append(f"❌ Terraform apply error:\n{e.stderr or str(e)}")

    return "\n".join(logs)




# def validate_and_fix_terraform_code(code: str, working_dir: str = ".") -> str:
#     """
#     Validates the Terraform code using `terraform validate`.
#     If it fails, uses OpenAI to fix the code based on error output.
#     Repeats until validation succeeds or max retries are hit.
#     Returns the final working Terraform code or error message.
#     """
#     cleaned_code = clean_terraform_code(code)
#     tf_file = os.path.join(working_dir, "main.tf")

#     iteration = 0
#     max_iterations = 5

#     while iteration < max_iterations:
#         iteration += 1

#         # Save the current version of code
#         with open(tf_file, "w") as f:
#             f.write(cleaned_code)

#         # Initialize Terraform (required before validate)
#         # Use capture_output=True to suppress init output unless there's an error
#         init_proc = subprocess.run(
#             ["terraform", "init", "-input=false", "-no-color"],  # Added -no-color for cleaner output
#             cwd=working_dir,
#             capture_output=True,
#             text=True
#         )
        
#         if init_proc.returncode != 0:
#             print(f"❌ Terraform init failed (iteration {iteration}):\n{init_proc.stderr.strip()}")
#             # If init fails, we might not be able to validate. Try to fix based on init error.
#             validation_error = init_proc.stderr.strip()
#             # If it's an init error, we might need a different prompt or give up.
#             # For now, treat it like a validation error for fixing.
#         else:
#             print(f"🔧 Terraform init successful (iteration {iteration})")
#             validation_error = ""

#         # Run terraform validate
#         validate_proc = subprocess.run(
#             ["terraform", "validate", "-no-color"],  # Added -no-color for cleaner output
#             cwd=working_dir,
#             capture_output=True,
#             text=True
#         )

#         if validate_proc.returncode == 0:
#             print(f"✅ Terraform code is valid on iteration {iteration}")
#             return cleaned_code

#         # If validation fails, extract the error
#         if not validation_error:  # Only use validate error if init didn't fail
#             validation_error = validate_proc.stderr.strip()
#         print(f"❌ Validation failed (iteration {iteration}):\n{validation_error}")

#         # Construct a prompt to fix the code using OpenAI
#         fix_prompt = f"""You are a Terraform expert.

# You are provided with Terraform HCL code that failed validation. Fix **all** the issues strictly based on the validation error shown.

# ### Original Invalid Terraform Code:
# ```hcl
# {cleaned_code}
# ```

# ### Validation Error:
# ```
# {validation_error}
# ```

# ### Instructions:
# Only return corrected, valid Terraform code. Do NOT include explanations, comments, or notes. Do NOT wrap the code in triple backticks.

# Fix all issues so the code becomes valid and production-ready."""

#         # Call OpenAI to fix the code
#         try:
#             response = client.chat.completions.create(
#                 model="gpt-4o",
#                 messages=[
#                     {"role": "system", "content": "You are a DevOps expert who writes Terraform."},
#                     {"role": "user", "content": fix_prompt}
#                 ],
#                 temperature=0.2,
#                 max_tokens=1500
#             )
#             fixed_code = response.choices[0].message.content
#             cleaned_code = clean_terraform_code(fixed_code)

#         except Exception as e:
#             return f"❌ OpenAI API call failed during fix attempt: {str(e)}"

#     return "❌ Could not produce valid Terraform code after multiple attempts."




def validate_and_fix_terraform_code(code: str, working_dir: str = TEMP_DIR) -> str:
    """
    Validates the Terraform code using `terraform validate`.
    If it fails, uses OpenAI to fix the code based on error output.
    Repeats until validation succeeds or max retries are hit.
    Saves the final validated code into `main.tf` inside the TEMP_DIR.

    Returns:
        str: Final validated Terraform code or error message.
    """
    cleaned_code = clean_terraform_code(code)
    tf_file = os.path.join(working_dir, "main.tf")

    iteration = 0
    max_iterations = 5

    while iteration < max_iterations:
        iteration += 1

        # Save the current version of code
        with open(tf_file, "w", encoding="utf-8") as f:
            f.write(cleaned_code)

        # Run terraform init
        init_proc = subprocess.run(
            ["terraform", "init", "-input=false", "-no-color"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )

        if init_proc.returncode != 0:
            print(f"❌ Terraform init failed (iteration {iteration}):\n{init_proc.stderr.strip()}")
            validation_error = init_proc.stderr.strip()
        else:
            print(f"🔧 Terraform init successful (iteration {iteration})")
            validation_error = ""

        # Run terraform validate
        validate_proc = subprocess.run(
            ["terraform", "validate", "-no-color"],
            cwd=working_dir,
            capture_output=True,
            text=True
        )

        if validate_proc.returncode == 0:
            print(f"✅ Terraform code is valid on iteration {iteration}")
            
            # ✅ Save validated code to TEMP_DIR/main.tf
            with open(tf_file, "w", encoding="utf-8") as f:
                f.write(cleaned_code + "\n")
            
            print(f"📁 Validated Terraform code saved to: {tf_file}")
            return cleaned_code

        # If validation fails, extract the error
        if not validation_error:
            validation_error = validate_proc.stderr.strip()
        print(f"❌ Validation failed (iteration {iteration}):\n{validation_error}")

        # Ask OpenAI to fix it
        fix_prompt = f"""You are a Terraform expert.

        You are provided with Terraform HCL code that failed validation. Fix **all** the issues strictly based on the validation error shown.

        ### Original Invalid Terraform Code:
        ```hcl
        {cleaned_code}
        ```
        ### Validation Error:
        {validation_error}

        ### Instructions:
        Only return corrected, valid Terraform code. Do NOT include explanations, comments, or notes. Do NOT wrap the code in triple backticks.

        Fix all issues so the code becomes valid and production-ready."""
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a DevOps expert who writes Terraform."},
                    {"role": "user", "content": fix_prompt}
                ],
                temperature=0.2,
                max_tokens=1500
            )
            fixed_code = response.choices[0].message.content
            cleaned_code = clean_terraform_code(fixed_code)

        except Exception as e:
            return f"❌ OpenAI API call failed during fix attempt: {str(e)}"

    return "❌ Could not produce valid Terraform code after multiple attempts."


def fetch_and_save_aws_resource_details(arns: list[str], inspector: DynamicAWSResourceInspector, project_name: str = "project_name") -> str:
    """
    Fetches AWS resource details for all ARNs, structures them, and writes to a JSON file.

    Args:
        arns (list[str]): List of AWS ARNs.
        inspector (DynamicAWSResourceInspector): Inspector to fetch details.
        project_name (str): Top-level key in the resulting JSON.

    Returns:
        str: Path to the saved JSON file.
    """
    aggregated_details = {project_name: {}}

    for arn in arns:
        print(f"\n{'=' * 100}")
        print(f"Fetching details for ARN: {arn}")
        print(f"{'=' * 100}")

        result = inspector.get_resource_details(arn)

        if "error" in result:
            print(f"❌ Failed to fetch details for {arn}: {result['error']}")
            continue

        resource_name = f"{result['service']}_{result['resource_id'].replace('/', '_')}"
        aggregated_details[project_name][resource_name] = result['details']

    # Save to JSON
    output_json_path = os.path.join(TEMP_DIR, f"{project_name}_resource_details.json")

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(aggregated_details, f, indent=2, default=str)

    print(f"\n📦 Aggregated resource details saved to: {output_json_path}")
    return output_json_path



def upload_terraform_to_minio(
    local_tf_dir: str,
    user_id: int,
    project_name: str,
    minio_endpoint: str = "storage.clouvix.com",
    minio_access_key: str = "clouvix@gmail.com",
    minio_secret_key: str = "Clouvix@bangalore2025",
    secure: bool = True
) -> str:
    """
    Uploads Terraform files to both MinIO and S3 (if configured).

    Args:
        local_tf_dir (str): Path to local Terraform project folder.
        user_id (int): User ID (for bucket naming).
        project_name (str): Project folder name inside bucket.

    Returns:
        str: Upload status summary.
    """
    bucket_name = f"terraform-workspaces-user-{user_id}"
    folder_name = f"{project_name}_terraform"

    minio_success = False
    s3_success = False

    try:
        # === Upload to MinIO ===
        minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=secure
        )

        if not minio_client.bucket_exists(bucket_name):
            print(f"🪣 Bucket `{bucket_name}` does not exist. Creating it...")
            minio_client.make_bucket(bucket_name)
        else:
            print(f"✅ MinIO bucket `{bucket_name}` exists.")

        print("📤 Uploading Terraform files to MinIO...")
        for root, _, files in os.walk(local_tf_dir):
            if ".terraform" in root:
                continue

            for file in files:
                if file.endswith(".json"):
                    continue

                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, local_tf_dir)
                object_key = f"{folder_name}/{relative_path}".replace("\\", "/")

                minio_client.fput_object(bucket_name, object_key, file_path)
                print(f"⬆️ MinIO: {object_key}")

        minio_success = True
    except Exception as e:
        print(f"❌ MinIO upload failed: {e}")

    # === Upload to S3 (if configured) ===
    try:
        s3_config = get_s3_connection_info_with_credentials(user_id)
        s3_bucket = s3_config["bucket"]
        s3_region = s3_config["region"]
        s3_prefix = s3_config.get("prefix", "")
        aws_access_key_id = s3_config.get("aws_access_key_id")
        aws_secret_access_key = s3_config.get("aws_secret_access_key")

        if s3_bucket and aws_access_key_id and aws_secret_access_key:
            s3 = boto3.client(
                's3',
                region_name=s3_region,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key
            )

            s3_folder_prefix = f"{s3_prefix}{folder_name}/" if s3_prefix else f"{folder_name}/"

            print("📤 Uploading Terraform files to S3...")
            for root, _, files in os.walk(local_tf_dir):
                if ".terraform" in root:
                    continue

                for file in files:
                    if file.endswith(".json"):
                        continue

                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, local_tf_dir)
                    object_key = f"{s3_folder_prefix}{relative_path}".replace("\\", "/")

                    s3.upload_file(file_path, s3_bucket, object_key)
                    print(f"⬆️ S3: {object_key}")

            s3_success = True
        else:
            print("⚠️ Skipping S3 upload – missing credentials or bucket info.")

    except Exception as e:
        print(f"❌ S3 upload failed: {e}")

    # === Final status message ===
    status = "Upload Summary:\n"
    status += "✅ MinIO upload successful.\n" if minio_success else "❌ MinIO upload failed.\n"
    status += "✅ S3 upload successful.\n" if s3_success else "⚠️ S3 upload skipped or failed.\n"
    return status



# def main():
#     try:
#         ACCESS_KEY, SECRET_KEY = get_aws_credentials_from_db(user_id=3)
#     except ValueError as e:
#         print(str(e))
#         return 
#     REGION = "us-east-1"
#     PROJECT_NAME = "migration"  
#     USER_ID = 3

#     inspector = DynamicAWSResourceInspector(ACCESS_KEY, SECRET_KEY, REGION)

#     test_arns = [
#         "arn:aws:ec2:us-east-1:010909987020:instance/i-0500881de5a5f5041",
#         "arn:aws:s3:::test-migration-bucket-clouvix"
#     ]

#     # Fetch details and save to JSON
#     output_json_path = fetch_and_save_aws_resource_details(test_arns, inspector, project_name="project_name")

#     # Load JSON
#     with open(output_json_path, "r", encoding="utf-8") as f:
#         all_config_data = json.load(f)

#     print(f"\n{'-' * 80}")
#     print("🛠️  Generating Terraform Code via GPT-4o for ALL RESOURCES...")
#     print(f"{'-' * 80}")

#     terraform_code = generate_terraform_from_resource_details(test_arns, inspector)

#     print(terraform_code)

#     print(f"\n{'-' * 80}")
#     print("🔍 Validating & fixing Terraform code...")
#     print(f"{'-' * 80}")

#     final_tf_code = validate_and_fix_terraform_code(terraform_code)
#     print("\n✅ Final Validated Terraform Code:\n")
#     print(final_tf_code)

#     main_tf_path = os.path.join(TEMP_DIR, "main.tf")


#     print(f"\n{'-' * 80}")
#     print("🚀 Importing & Applying Terraform configuration... (Only first ARN for now)")
#     print(f"{'-' * 80}")

#     result = import_and_apply_for_resource(
#     main_tf_path=main_tf_path,
#     arns=test_arns,
#     user_id=USER_ID,
#     project_name=PROJECT_NAME
# )

#     print(result)

#     # After apply step
#     upload_status = upload_terraform_to_minio(
#         local_tf_dir=TEMP_DIR,
#         user_id=3,
#         project_name="project_name"
#     )
#     print(upload_status)

    
#     🧹 Delete TEMP_DIR after everything is done
#     if os.path.exists(TEMP_DIR):
#         print(f"\n🧹 Cleaning up temporary folder: {TEMP_DIR}")
#         shutil.rmtree(TEMP_DIR)
#         print("✅ Temporary folder deleted.")
#     else:
#         print("⚠️ TEMP_DIR does not exist. Nothing to clean.")


        
# if __name__ == "__main__":
#     main()