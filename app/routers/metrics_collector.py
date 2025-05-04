import boto3
import json
import datetime
import logging
import os
import time
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class AWSMetricsCollector:
    def __init__(self, aws_access_key_id, aws_secret_access_key, region_name):
        """Initialize the AWS Metrics Collector with credentials"""
        self.session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
        self.ec2_client = self.session.client('ec2')
        self.s3_client = self.session.client('s3')
        self.rds_client = self.session.client('rds')
        self.lambda_client = self.session.client('lambda')
        self.cloudwatch = self.session.client('cloudwatch')
        self.sts_client = self.session.client('sts')
        self.account_id = self.sts_client.get_caller_identity()['Account']
        self.region_name = region_name
        self.metrics_data = {
            'EC2': [],
            'S3': [],
            'RDS': [],
            'Lambda': []
        }

    def collect_ec2_metrics(self):
        """Collect EC2 instance metrics with recommendations and ARN"""
        try:
            paginator = self.ec2_client.get_paginator('describe_instances')
            instances = []
            
            for page in paginator.paginate():
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        if instance['State']['Name'] == 'running':
                            instances.append(instance)
            
            logger.info(f"Found {len(instances)} running EC2 instances")
            
            for instance in instances:
                instance_id = instance['InstanceId']
                instance_type = instance['InstanceType']
                # Construct EC2 ARN
                instance_arn = f"arn:aws:ec2:{self.region_name}:{self.account_id}:instance/{instance_id}"
                
                instance_name = None
                if 'Tags' in instance:
                    for tag in instance['Tags']:
                        if tag['Key'] == 'Name':
                            instance_name = tag['Value']
                            break
                
                if not instance_name:
                    instance_name = instance_id
                
               # logger.info(f"Collecting metrics for EC2 instance {instance_id} ({instance_type}) - {instance_name}")
                
                cpu_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/EC2',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                    StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                    EndTime=datetime.datetime.now(),
                    Period=86400,
                    Statistics=['Average', 'Maximum']
                )
                
                recommendation = None
                if cpu_response['Datapoints']:
                    avg_cpu = sum(point['Average'] for point in cpu_response['Datapoints']) / len(cpu_response['Datapoints'])
                    max_cpu = max(point['Maximum'] for point in cpu_response['Datapoints']) if cpu_response['Datapoints'] else 0
                    
                    if avg_cpu < 20:
                        recommendation = "Downsize the instance."
                    elif avg_cpu > 80:
                        recommendation = "Upgrade the instance."
                    
                    daily_metrics = []
                    for point in sorted(cpu_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'AvgCPU': f"{point['Average']:.2f}%",
                            'MaxCPU': f"{point['Maximum']:.2f}%"
                        })
                    
                    self.metrics_data['EC2'].append({
                        'ARN': instance_arn,
                        'InstanceId': instance_id,
                        'InstanceName': instance_name,
                        'InstanceType': instance_type,
                        'AvgCPU': f"{avg_cpu:.2f}%",
                        'MaxCPU': f"{max_cpu:.2f}%",
                        'Recommendation': recommendation,
                        'DailyMetrics': daily_metrics
                    })
                    
                    if recommendation:
                        print(f"  Recommendation: {recommendation}")
                    print("-" * 50)
                else:
                    logger.warning(f"No CloudWatch data available for instance {instance_id}")
                    self.metrics_data['EC2'].append({
                        'ARN': instance_arn,
                        'InstanceId': instance_id,
                        'InstanceName': instance_name,
                        'InstanceType': instance_type,
                        'AvgCPU': None,
                        'MaxCPU': None,
                        'DailyMetrics': [],
                        'Recommendation': None
                    })
        
        except Exception as e:
            logger.error(f"Error collecting EC2 metrics: {e}")

    def collect_s3_metrics(self):
        """Collect S3 bucket metrics with ARN"""
        try:
            buckets = self.s3_client.list_buckets()
            logger.info(f"Found {len(buckets['Buckets'])} S3 buckets")

            for bucket in buckets['Buckets']:
                bucket_name = bucket['Name']
                bucket_region = self.get_bucket_region(bucket_name)
                # Construct S3 ARN
                bucket_arn = f"arn:aws:s3:::{bucket_name}"

                if bucket_region != self.session.region_name:
                    logger.info(f"Skipping bucket {bucket_name} as it's in a different region: {bucket_region}")
                    continue

                bucket_metrics = {
                    'BucketSizeBytes': 0,
                    'NumberOfObjects': 0
                }

                try:
                    size_metrics = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='BucketSizeBytes',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'StandardStorage'}
                        ],
                        StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                        EndTime=datetime.datetime.now(),
                        Period=86400,
                        Statistics=['Average']
                    )

                    if not size_metrics['Datapoints']:
                        logger.warning(f"No CloudWatch size data for bucket {bucket_name} in the last 14 days")
                    else:
                        latest_point = max(size_metrics['Datapoints'], key=lambda x: x['Timestamp'])
                        bucket_metrics['BucketSizeBytes'] = latest_point['Average']
                        bucket_size_mb = latest_point['Average'] / (1024 * 1024)
                        bucket_metrics['BucketSizeMB'] = round(bucket_size_mb, 2)

                    object_count_metrics = self.cloudwatch.get_metric_statistics(
                        Namespace='AWS/S3',
                        MetricName='NumberOfObjects',
                        Dimensions=[
                            {'Name': 'BucketName', 'Value': bucket_name},
                            {'Name': 'StorageType', 'Value': 'AllStorageTypes'}
                        ],
                        StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                        EndTime=datetime.datetime.now(),
                        Period=86400,
                        Statistics=['Average']
                    )

                    if not object_count_metrics['Datapoints']:
                        logger.warning(f"No CloudWatch object count data for bucket {bucket_name} in the last 14 days")
                    else:
                        latest_point = max(object_count_metrics['Datapoints'], key=lambda x: x['Timestamp'])
                        bucket_metrics['NumberOfObjects'] = int(latest_point['Average'])

                except ClientError as e:
                    logger.warning(f"Error getting CloudWatch metrics for bucket {bucket_name}: {e}")
                    try:
                        logger.info(f"Falling back to list_object_versions for {bucket_name}")
                        total_size = 0
                        total_objects = 0
                        paginator = self.s3_client.get_paginator('list_object_versions')
                        for page in paginator.paginate(Bucket=bucket_name):
                            if 'Versions' in page:
                                for version in page['Versions']:
                                    total_size += version['Size']
                                    total_objects += 1
                        bucket_metrics['BucketSizeBytes'] = total_size
                        bucket_metrics['BucketSizeMB'] = round(total_size / (1024 * 1024), 2)
                        bucket_metrics['NumberOfObjects'] = total_objects
                    except ClientError as list_error:
                        logger.warning(f"Error listing objects for bucket {bucket_name}: {list_error}")

                self.metrics_data['S3'].append({
                    'ARN': bucket_arn,
                    'BucketName': bucket_name,
                    'BucketRegion': bucket_region,
                    'Metrics': bucket_metrics
                })


        except Exception as e:
            logger.error(f"Error collecting S3 metrics: {e}")

    def collect_rds_metrics(self):
        """Collect RDS instance metrics with recommendations and ARN"""
        try:
            response = self.rds_client.describe_db_instances()
            instances = response['DBInstances']
            
            logger.info(f"Found {len(instances)} RDS instances")

            for instance in instances:
                db_instance_identifier = instance['DBInstanceIdentifier']
                db_instance_class = instance['DBInstanceClass']
                engine = instance['Engine']
                db_instance_status = instance['DBInstanceStatus']
                # Get RDS ARN directly from the response
                db_instance_arn = instance['DBInstanceArn']

                if db_instance_status != 'available':
                    logger.info(f"Skipping RDS instance {db_instance_identifier} (status: {db_instance_status})")
                    continue

                #logger.info(f"Collecting metrics for RDS instance {db_instance_identifier} ({db_instance_class})")

                cpu_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/RDS',
                    MetricName='CPUUtilization',
                    Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_instance_identifier}],
                    StartTime=datetime.datetime.now() - datetime.timedelta(days=14),
                    EndTime=datetime.datetime.now(),
                    Period=86400,
                    Statistics=['Average', 'Maximum']
                )

                rds_metrics = {
                    'CPUUtilization': {
                        'Average': 0,
                        'Maximum': 0,
                        'DailyMetrics': []
                    }
                }

                recommendation = None
                if cpu_response['Datapoints']:
                    avg_cpu = sum(point['Average'] for point in cpu_response['Datapoints']) / len(cpu_response['Datapoints'])
                    max_cpu = max(point['Maximum'] for point in cpu_response['Datapoints']) if cpu_response['Datapoints'] else 0

                    if avg_cpu < 20:
                        recommendation = "Downsize the RDS instance."
                    elif avg_cpu > 80:
                        recommendation = "Upgrade the RDS instance."

                    daily_metrics = []
                    for point in sorted(cpu_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'AvgCPU': f"{point['Average']:.2f}%",
                            'MaxCPU': f"{point['Maximum']:.2f}%"
                        })

                    rds_metrics['CPUUtilization'] = {
                        'Average': f"{avg_cpu:.2f}%",
                        'Maximum': f"{max_cpu:.2f}%",
                        'DailyMetrics': daily_metrics
                    }

                    self.metrics_data['RDS'].append({
                        'ARN': db_instance_arn,
                        'DBInstanceIdentifier': db_instance_identifier,
                        'DBInstanceClass': db_instance_class,
                        'Engine': engine,
                        'Metrics': rds_metrics,
                        'Recommendation': recommendation
                    })


                    if recommendation:
                        print(f"  Recommendation: {recommendation}")
                    print("-" * 50)
                else:
                    logger.warning(f"No CloudWatch data available for RDS instance {db_instance_identifier}")
                    self.metrics_data['RDS'].append({
                        'ARN': db_instance_arn,
                        'DBInstanceIdentifier': db_instance_identifier,
                        'DBInstanceClass': db_instance_class,
                        'Engine': engine,
                        'Metrics': rds_metrics,
                        'Recommendation': None
                    })

        except Exception as e:
            logger.error(f"Error collecting RDS metrics: {e}")

    def collect_lambda_metrics(self):
        """Collect Lambda function metrics with recommendations and ARN"""
        try:
            paginator = self.lambda_client.get_paginator('list_functions')
            functions = []
            
            for page in paginator.paginate():
                functions.extend(page['Functions'])
            
            logger.info(f"Found {len(functions)} Lambda functions")

            for function in functions:
                function_name = function['FunctionName']
                runtime = function.get('Runtime', 'N/A')
                # Get Lambda ARN directly from the response
                function_arn = function['FunctionArn']
                
              #  logger.info(f"Collecting metrics for Lambda function {function_name} (Runtime: {runtime})")

                lambda_metrics = {
                    'Invocations': {
                        'Total': 0,
                        'DailyMetrics': []
                    },
                    'Duration': {
                        'Average': 0,
                        'Maximum': 0,
                        'DailyMetrics': []
                    },
                    'Errors': {
                        'Total': 0,
                        'DailyMetrics': []
                    },
                    'Throttles': {
                        'Total': 0,
                        'DailyMetrics': []
                    }
                }

                start_time = datetime.datetime.now() - datetime.timedelta(days=14)
                end_time = datetime.datetime.now()

                invocations_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Invocations',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Sum']
                )

                if invocations_response['Datapoints']:
                    total_invocations = sum(point['Sum'] for point in invocations_response['Datapoints'])
                    daily_metrics = []
                    for point in sorted(invocations_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'Invocations': int(point['Sum'])
                        })
                    lambda_metrics['Invocations'] = {
                        'Total': int(total_invocations),
                        'DailyMetrics': daily_metrics
                    }

                duration_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Duration',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Average', 'Maximum']
                )

                recommendation = None
                if duration_response['Datapoints']:
                    avg_duration = sum(point['Average'] for point in duration_response['Datapoints']) / len(duration_response['Datapoints'])
                    max_duration = max(point['Maximum'] for point in duration_response['Datapoints']) if duration_response['Datapoints'] else 0

                    if avg_duration >= 810000:
                        recommendation = "Function execution time is too high, consider optimizing the function."

                    daily_metrics = []
                    for point in sorted(duration_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'AvgDuration': f"{point['Average']:.2f} ms",
                            'MaxDuration': f"{point['Maximum']:.2f} ms"
                        })
                    lambda_metrics['Duration'] = {
                        'Average': f"{avg_duration:.2f} ms",
                        'Maximum': f"{max_duration:.2f} ms",
                        'DailyMetrics': daily_metrics
                    }

                errors_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Sum']
                )

                if errors_response['Datapoints']:
                    total_errors = sum(point['Sum'] for point in errors_response['Datapoints'])
                    daily_metrics = []
                    for point in sorted(errors_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'Errors': int(point['Sum'])
                        })
                    lambda_metrics['Errors'] = {
                        'Total': int(total_errors),
                        'DailyMetrics': daily_metrics
                    }

                throttles_response = self.cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Throttles',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=['Sum']
                )

                if throttles_response['Datapoints']:
                    total_throttles = sum(point['Sum'] for point in throttles_response['Datapoints'])
                    daily_metrics = []
                    for point in sorted(throttles_response['Datapoints'], key=lambda x: x['Timestamp']):
                        daily_metrics.append({
                            'Date': point['Timestamp'].strftime('%Y-%m-%d'),
                            'Throttles': int(point['Sum'])
                        })
                    lambda_metrics['Throttles'] = {
                        'Total': int(total_throttles),
                        'DailyMetrics': daily_metrics
                    }

                self.metrics_data['Lambda'].append({
                    'ARN': function_arn,
                    'FunctionName': function_name,
                    'Runtime': runtime,
                    'Metrics': lambda_metrics,
                    'Recommendation': recommendation
                })

                if recommendation:
                    print(f"  Recommendation: {recommendation}")
                print("-" * 50)

        except Exception as e:
            logger.error(f"Error collecting Lambda metrics: {e}")

    def get_bucket_region(self, bucket_name):
        """Get the region of an S3 bucket"""
        try:
            location = self.s3_client.get_bucket_location(Bucket=bucket_name)
            region = location['LocationConstraint']
            if region is None:
                return 'us-east-1'
            return region
        except Exception as e:
            logger.warning(f"Error getting region for bucket {bucket_name}: {e}")
            return 'unknown'

    def run_collection(self):
        """Run the complete metrics collection"""
        try:
            self.collect_ec2_metrics()
            self.collect_s3_metrics()
            self.collect_rds_metrics()
            self.collect_lambda_metrics()
            
            return self.metrics_data
        
        except Exception as e:
            logger.error(f"Error running metrics collection: {e}")
            raise

def fetch_and_save_metrics():
    output_file = 'aws_metrics.json'
    while True:
        try:
            print("Starting AWS metrics collection cycle")
            access_key = os.getenv('AWS_ACCESS_KEY')
            secret_key = os.getenv('AWS_SECRET_KEY')
            region = os.getenv('AWS_REGION', 'us-east-1')
            
            if not access_key or not secret_key:
                logger.error("AWS credentials not found in environment variables")
                time.sleep(30)
                continue

            print("Initializing AWSMetricsCollector")
            collector = AWSMetricsCollector(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region
            )
            
            logger.info("Running metrics collection")
            metrics_data = collector.run_collection()
            
            print(f"Saving metrics to {output_file}")
            with open(output_file, 'w') as f:
                json.dump({
                    'generatedAt': datetime.datetime.now().isoformat(),
                    'metrics': metrics_data
                }, f, indent=2)
            
                        # Insert metrics into database
            logger.info("Inserting metrics into database")
            insert_metrics_to_db()
            
            print(f"Metrics collection cycle completed. Sleeping for 120 seconds")
        
        except Exception as e:
            logger.error(f"Error in metrics collection cycle: {str(e)}", exc_info=True)
        
        time.sleep(120)


# # Database setup
# DATABASE_URL = os.getenv('DATABASE_URL')
# if not DATABASE_URL:
#     raise ValueError("DATABASE_URL not found in environment variables")

# engine = create_engine(DATABASE_URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# def insert_metrics_to_db():
#     """Insert metrics from aws_metrics.json into the metrics table."""
#     try:
#         # Read metrics from aws_metrics.json
#         output_file = 'aws_metrics.json'
#         if not os.path.exists(output_file):
#             logger.error(f"Metrics file {output_file} not found")
#             return

#         # Get AWS credentials from environment
#         aws_access_key = os.getenv('AWS_ACCESS_KEY')
#         aws_secret_access_key = os.getenv('AWS_SECRET_KEY')
#         if not aws_access_key or not aws_secret_access_key:
#             logger.error("AWS credentials not found in environment variables")
#             return

#         with open(output_file, 'r') as f:
#             data = json.load(f)

#         generated_at = data.get('generatedAt')
#         metrics_data = data.get('metrics', {})

#         if not generated_at or not metrics_data:
#             logger.error("Invalid metrics data format in aws_metrics.json")
#             return

#         # Create a database session
#         with SessionLocal() as session:
#             try:
#                 # Insert metrics for each resource type
#                 for resource_type, resources in metrics_data.items():
#                     for resource in resources:
#                         arn = resource.get('ARN')
#                         resource_identifier = (
#                             resource.get('InstanceId') or
#                             resource.get('BucketName') or
#                             resource.get('DBInstanceIdentifier') or
#                             resource.get('FunctionName')
#                         )

#                         # Prepare metrics_data for JSONB
#                         resource_metrics = {k: v for k, v in resource.items() if k != 'ARN'}
#                         # Remove fields not stored in metrics_data JSONB
#                         for key in ['Recommendation', 'InstanceId', 'BucketName', 
#                                   'DBInstanceIdentifier', 'FunctionName']:
#                             if key in resource_metrics:
#                                 del resource_metrics[key]

#                         # SQL query to insert or update metrics
#                         query = """
#                             INSERT INTO metrics (
#                                 generated_at, resource_type, arn, resource_identifier,
#                                 metrics_data, aws_access_key, aws_secret_access_key,
#                                 created_at, updated_at
#                             ) VALUES (
#                                 :generated_at, :resource_type, :arn, :resource_identifier,
#                                 :metrics_data, :aws_access_key, :aws_secret_access_key,
#                                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
#                             )
#                             ON CONFLICT ON CONSTRAINT unique_arn_resource_type
#                             DO UPDATE SET
#                                 generated_at = EXCLUDED.generated_at,
#                                 metrics_data = EXCLUDED.metrics_data,
#                                 aws_access_key = EXCLUDED.aws_access_key,
#                                 aws_secret_access_key = EXCLUDED.aws_secret_access_key,
#                                 updated_at = CURRENT_TIMESTAMP
#                         """

#                         session.execute(text(query), {
#                             'generated_at': generated_at,
#                             'resource_type': resource_type,
#                             'arn': arn,
#                             'resource_identifier': resource_identifier,
#                             'metrics_data': json.dumps(resource_metrics),
#                             'aws_access_key': aws_access_key,
#                             'aws_secret_access_key': aws_secret_access_key
#                         })

#                 session.commit()
#                 logger.info("Successfully inserted/updated metrics")

#             except Exception as e:
#                 session.rollback()
#                 logger.error(f"Error inserting metrics into database: {str(e)}")
#                 raise

#     except Exception as e:
#         logger.error(f"Error in insert_metrics_to_db: {str(e)}")
def fetch_aws_credentials():
    """Fetch AWS credentials from the connections table where type='aws'."""
    try:
        with SessionLocal() as session:
            query = """
                SELECT userid, connection_json
                FROM connections
                WHERE type = 'aws'
            """
            result = session.execute(text(query)).fetchall()
            credentials_list = []

            for row in result:
                # Access Row object using column names
                userid = row.userid  # Use attribute access for Row objects
                connection_json = row.connection_json
                
                # Parse the JSONB connection_json
                try:
                    connection_data = json.loads(connection_json)
                    access_key = None
                    secret_key = None
                    region = 'us-east-1'  # Default region if not specified

                    for item in connection_data:
                        if item['key'] == 'AWS_ACCESS_KEY_ID':
                            access_key = item['value']
                        elif item['key'] == 'AWS_SECRET_ACCESS_KEY':
                            secret_key = item['value']
                        elif item['key'] == 'AWS_REGION':
                            region = item['value']

                    if access_key and secret_key:
                        credentials_list.append({
                            'userid': userid,
                            'access_key': access_key,
                            'secret_key': secret_key,
                            'region': region
                        })
                    else:
                        logger.warning(f"Missing AWS credentials for userid {userid}")
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing connection_json for userid {userid}: {e}")
            
            return credentials_list

    except Exception as e:
        logger.error(f"Error fetching AWS credentials from connections table: {e}")
        return []

def fetch_and_save_metrics():
    output_file = 'aws_metrics.json'
    while True:
        try:
            print("Starting AWS metrics collection cycle")
            
            # Fetch AWS credentials from connections table
            credentials_list = fetch_aws_credentials()
            
            if not credentials_list:
                logger.error("No valid AWS credentials found in connections table")
                time.sleep(30)
                continue

            for creds in credentials_list:
                userid = creds['userid']
                access_key = creds['access_key']
                secret_key = creds['secret_key']
                region = creds['region']

                print(f"Collecting metrics for userid {userid} in region {region}")
                try:
                    # Initialize AWSMetricsCollector and collect metrics
                    collector = AWSMetricsCollector(
                        aws_access_key_id=access_key,
                        aws_secret_access_key=secret_key,
                        region_name=region
                    )
                    
                    logger.info(f"Running metrics collection for userid {userid}")
                    metrics_data = collector.run_collection()
                    
                    # Save metrics to JSON file (optional, can be removed if only DB storage is needed)
                    print(f"Saving metrics to {output_file} for userid {userid}")
                    with open(f"{userid}_{output_file}", 'w') as f:
                        json.dump({
                            'generatedAt': datetime.datetime.now().isoformat(),
                            'metrics': metrics_data,
                            'userid': userid
                        }, f, indent=2)
                    
                    # Insert metrics into database
                    logger.info(f"Inserting metrics into database for userid {userid}")
                    insert_metrics_to_db(metrics_data, userid)
                    
                    print(f"Metrics collection completed for userid {userid}")
                
                except ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidClientTokenId':
                        logger.error(f"Invalid AWS credentials for userid {userid}: {str(e)}")
                        print(f"Skipping userid {userid} due to invalid credentials")
                        continue
                    else:
                        logger.error(f"AWS error for userid {userid}: {str(e)}")
                        raise  # Re-raise other AWS errors
                except Exception as e:
                    logger.error(f"Error collecting metrics for userid {userid}: {str(e)}", exc_info=True)
                    print(f"Skipping userid {userid} due to error: {str(e)}")
                    continue
            
            print("Metrics collection cycle completed for all AWS accounts. Sleeping for 120 seconds")
        
        except Exception as e:
            logger.error(f"Error in metrics collection cycle: {str(e)}", exc_info=True)
        
        time.sleep(120)

def insert_metrics_to_db(metrics_data, userid):
    """Insert metrics into the metrics table with userid."""
    try:
        generated_at = datetime.datetime.now().isoformat()

        # Create a database session
        with SessionLocal() as session:
            try:
                # Insert metrics for each resource type
                for resource_type, resources in metrics_data.items():
                    for resource in resources:
                        arn = resource.get('ARN')
                        resource_identifier = (
                            resource.get('InstanceId') or
                            resource.get('BucketName') or
                            resource.get('DBInstanceIdentifier') or
                            resource.get('FunctionName')
                        )

                        # Prepare metrics_data for JSONB
                        resource_metrics = {k: v for k, v in resource.items() if k != 'ARN'}
                        # Remove fields not stored in metrics_data JSONB
                        for key in ['Recommendation', 'InstanceId', 'BucketName', 
                                  'DBInstanceIdentifier', 'FunctionName']:
                            if key in resource_metrics:
                                del resource_metrics[key]

                        # SQL query to insert or update metrics
                        query = """
                            INSERT INTO metrics (
                                generated_at, resource_type, arn, resource_identifier,
                                metrics_data, userid,
                                created_at, updated_at
                            ) VALUES (
                                :generated_at, :resource_type, :arn, :resource_identifier,
                                :metrics_data, :userid,
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                            ON CONFLICT ON CONSTRAINT unique_arn_resource_type
                            DO UPDATE SET
                                generated_at = EXCLUDED.generated_at,
                                metrics_data = EXCLUDED.metrics_data,
                                userid = EXCLUDED.userid,
                                updated_at = CURRENT_TIMESTAMP
                        """

                        session.execute(text(query), {
                            'generated_at': generated_at,
                            'resource_type': resource_type,
                            'arn': arn,
                            'resource_identifier': resource_identifier,
                            'metrics_data': json.dumps(resource_metrics),
                            'userid': userid
                        })

                session.commit()
                logger.info(f"Successfully inserted/updated metrics for userid {userid}")

            except Exception as e:
                session.rollback()
                logger.error(f"Error inserting metrics into database for userid {userid}: {str(e)}")
                raise

    except Exception as e:
        logger.error(f"Error in insert_metrics_to_db for userid {userid}: {str(e)}")