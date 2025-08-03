def run_ec2_rds_recommendation_scheduler():
    from app.core.rds_ec2_recommendation import (
        get_boto3_session, fetch_arns_grouped_by_user_id, extract_instance_info_from_arn,
        describe_ec2_instance, describe_rds_instance, get_pricing_info,
        get_configured_cloudwatch_metrics, generate_recommendations,
        create_or_update_metrics, generate_llm_recommendation, insert_or_update,
        display_results
    )
    from app.database import SessionLocal
    from botocore.exceptions import ClientError, NoCredentialsError
    import re

    try:
        session = get_boto3_session()
        arns_by_user = fetch_arns_grouped_by_user_id()
        if not arns_by_user:
            print("\nNo processable ARNs found. Exiting.")
            return

        print("\n==================================================")
        print("      STARTING AWS COST & RIGHTSIZING ADVISOR     ")
        print("==================================================")

        for user_id, arns in arns_by_user.items():
            print(f"\n\n--- Processing User ID: {user_id} ---")
            for arn in arns:
                try:
                    print(f"\n🔍 Processing ARN: {arn}")
                    instance_id, region, service_type = extract_instance_info_from_arn(arn)

                    describe_func = describe_ec2_instance if service_type == 'EC2' else describe_rds_instance
                    instance_details = describe_func(instance_id, region, session)

                    current_pricing = get_pricing_info(session, instance_details)
                    if not current_pricing:
                        print(f"  - Skipping {arn} as current pricing could not be determined.")
                        continue

                    collected_metrics = get_configured_cloudwatch_metrics(session, region, service_type, instance_id)

                    if collected_metrics:
                        db = SessionLocal()
                        try:
                            create_or_update_metrics(
                                db=db,
                                userid=user_id,
                                arn=arn,
                                resource_type=service_type,
                                metrics_data=collected_metrics,
                                additional_info=instance_details
                            )
                        finally:
                            db.close()

                    action, new_type = generate_recommendations(instance_details, collected_metrics)
                    recommendation_package = None

                    if action and new_type:
                        new_instance_details = instance_details.copy()
                        new_instance_details['InstanceType'] = new_type
                        new_pricing = get_pricing_info(session, new_instance_details)

                        if new_pricing:
                            recommendation_package = (action, new_type, new_pricing)

                            # LLM Recommendation logic
                            current_total_annual = (current_pricing["compute_hourly"] * 24 * 365) + (current_pricing.get("storage_monthly", 0) * 12)
                            new_total_annual = (new_pricing["compute_hourly"] * 24 * 365) + (new_pricing.get("storage_monthly", 0) * 12)
                            savings = max(current_total_annual - new_total_annual, 0)
                            percent_savings = (savings / current_total_annual) * 100 if current_total_annual > 0 else 0

                            llm_text = generate_llm_recommendation(
                                resource_display_name=f"AWS {service_type}",
                                instance_type=instance_details["InstanceType"],
                                suggested_instance=new_type,
                                cost_hourly=new_pricing["compute_hourly"],
                                cost_saving=savings,
                                percent_saving=percent_savings
                            )

                            action_text = impact_text = savings_text = None
                            try:
                                match = re.search(r"\d*\.*\s*Action:\s*(.+?)\n+\d*\.*\s*Impact:\s*(.+?)\n+\d*\.*\s*Savings:\s*(.+)", llm_text, re.DOTALL | re.IGNORECASE)
                                if match:
                                    action_text = {"text": match.group(1).strip()}
                                    impact_text = {"text": match.group(2).strip()}
                                    savings_text = {"text": match.group(3).strip()}
                            except Exception as e:
                                print(f"⚠️ Failed to parse LLM response: {e}")

                            # Save to DB
                            db = SessionLocal()
                            try:
                                insert_or_update(
                                    db=db,
                                    userid=user_id,
                                    resource_type=service_type,
                                    arn=arn,
                                    recommendation_text=llm_text,
                                    action=action_text,
                                    impact=impact_text,
                                    savings=savings_text
                                )
                            finally:
                                db.close()

                    display_results(instance_details, current_pricing, recommendation_package)

                except (ValueError, ClientError) as e:
                    print(f"❌ Error processing ARN {arn}: {e}")
                finally:
                    print("--------------------------------------------------")

    except NoCredentialsError as e:
        print(f"\n❌ AWS Credentials Error: {e}")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred in the cost scheduler: {e}")
