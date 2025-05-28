import os
import json
import gzip
import shutil
import tempfile
import pandas as pd
import boto3
from io import StringIO
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from datetime import datetime

# Load env variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Setup DB session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()


def process_user_cur(userid, aws_access_key, aws_secret_key, bucket_name):
    print(f"\n[INFO] Processing user {userid}, bucket: {bucket_name}")

    # Setup S3 client with user credentials
    s3 = boto3.client(
        's3',
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )

    # Find latest .csv.gz file
    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
    except Exception as e:
        print(f"[ERROR] Cannot list objects in bucket '{bucket_name}': {e}")
        return

    if 'Contents' not in response:
        print(f"[WARN] No contents found in bucket '{bucket_name}'")
        return

    csv_gz_key = None
    for obj in sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True):
        if obj['Key'].endswith('.csv.gz'):
            csv_gz_key = obj['Key']
            break

    if not csv_gz_key:
        print(f"[WARN] No .csv.gz file found in bucket '{bucket_name}'")
        return

    print(f"[INFO] Found latest CUR file: {csv_gz_key}")

    # Prepare temp folder and paths
    temp_dir = tempfile.mkdtemp()
    gz_path = os.path.join(temp_dir, "report.csv.gz")
    csv_path = os.path.join(temp_dir, "report.csv")

    # Download and extract
    try:
        with open(gz_path, 'wb') as f:
            s3.download_fileobj(bucket_name, csv_gz_key, f)

        with gzip.open(gz_path, 'rb') as f_in:
            with open(csv_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    except Exception as e:
        print(f"[ERROR] Failed to download/extract CUR for user {userid}: {e}")
        shutil.rmtree(temp_dir)
        return

    print(f"[INFO] CUR file extracted to: {csv_path}")

    # Load CSV and preprocess
    try:
        df = pd.read_csv(csv_path)
        df['usage_date'] = pd.to_datetime(df['lineItem/UsageStartDate'], errors='coerce').dt.date
        df['lineItem/UnblendedCost'] = pd.to_numeric(df['lineItem/UnblendedCost'], errors='coerce').fillna(0)
        df['lineItem/UsageAmount'] = pd.to_numeric(df['lineItem/UsageAmount'], errors='coerce').fillna(0)
    except Exception as e:
        print(f"[ERROR] Failed to load/process CSV for user {userid}: {e}")
        shutil.rmtree(temp_dir)
        return

    # Process data by date and product
    with engine.begin() as conn:
        for (date, product_name), group in df.groupby(['usage_date', 'product/ProductName']):
            if pd.isna(date) or pd.isna(product_name):
                continue

            daily_product_data = group.groupby(
                ['lineItem/ResourceId']
            ).agg(
                total_cost=('lineItem/UnblendedCost', 'sum'),
                total_usage=('lineItem/UsageAmount', 'sum')
            ).reset_index()

            details = []

            for _, row in daily_product_data.iterrows():
                raw_resource_id = row['lineItem/ResourceId']
                resource_id = raw_resource_id

                if isinstance(resource_id, str) and not resource_id.startswith("arn:"):
                    if "Amazon Simple Storage Service" in product_name:
                        resource_id = f"arn:aws:s3:::{raw_resource_id}"
                    elif "AWS Lambda" in product_name:
                        resource_id = f"arn:aws:lambda:us-east-1::function:{raw_resource_id}"
                    elif "Amazon Elastic Compute Cloud" in product_name:
                        resource_id = f"arn:aws:ec2:us-east-1::instance/{raw_resource_id}"
                    else:
                        resource_id = raw_resource_id  # fallback

                details.append({
                    "arn": resource_id,
                    "total_cost": round(row['total_cost'], 4),
                    "total_usage": round(row['total_usage'], 4)
                })

            # Create JSON for this specific date and product
            daily_product_report = {
                "details": details,
                "total_cost": round(daily_product_data['total_cost'].sum(), 4)
            }

            # Insert or update daily product report in DB
            conn.execute(
                text("""
                    INSERT INTO cur_report (userid, usage_date, product_name, report_json, updated_at)
                    VALUES (:userid, :usage_date, :product_name, :report_json, :updated_at)
                    ON CONFLICT (userid, usage_date, product_name)
                    DO UPDATE SET
                        report_json = EXCLUDED.report_json,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "userid": userid,
                    "usage_date": date,
                    "product_name": product_name,
                    "report_json": json.dumps(daily_product_report),
                    "updated_at": datetime.utcnow()
                }
            )

            print(f"[SUCCESS] Stored report for user {userid}, date {date}, product {product_name}")

    # Cleanup temp files
    shutil.rmtree(temp_dir)

def run_cost_scheduler():
    # Fetch all user credentials & buckets from DB
    cur_bucket_rows = session.execute(text("""
        SELECT userid, connection_json
        FROM connections
        WHERE type = 'cur_bucket'
    """)).fetchall()

    for row in cur_bucket_rows:
        userid = row.userid
        connection_data = row.connection_json  # already parsed

        bucket_name = next((item['value'] for item in connection_data if item.get('key') == 'aws_cur_bucket'), None)
        if not bucket_name:
            print(f"[WARN] User {userid}: No bucket found, skipping.")
            continue

        aws_row = session.execute(text("""
            SELECT connection_json
            FROM connections
            WHERE userid = :userid AND type = 'aws'
        """), {'userid': userid}).fetchone()

        if not aws_row:
            print(f"[WARN] User {userid}: No AWS credentials found, skipping.")
            continue

        try:
            aws_data = json.loads(aws_row.connection_json)
        except json.JSONDecodeError:
            print(f"[WARN] User {userid}: Invalid AWS JSON, skipping.")
            continue

        aws_access_key = next((item['value'] for item in aws_data if item.get('key') == 'AWS_ACCESS_KEY_ID'), None)
        aws_secret_key = next((item['value'] for item in aws_data if item.get('key') == 'AWS_SECRET_ACCESS_KEY'), None)

        if not aws_access_key or not aws_secret_key:
            print(f"[WARN] User {userid}: Missing AWS keys, skipping.")
            continue

        # Call the processing function for this user
        process_user_cur(userid, aws_access_key, aws_secret_key, bucket_name)

    session.close()
