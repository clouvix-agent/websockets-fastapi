from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import general, auth, connections, inventory, workspace, recommendation_route, cost_endpoint, terraform, github , existing_to_tf,drift
from app.database import engine, Base
from app.routers.all_threads import start_background_threads
from app.scheduled_jobs import drift_script_standalone

# APScheduler import
from apscheduler.schedulers.background import BackgroundScheduler

# Import your scheduler job function
from app.scheduled_jobs.terraform_inventory import fetch_all_state_files
from app.routers.cost_schedular_code import run_cost_scheduler
from app.scheduled_jobs.drift_detection import run_daily_drift_detection_job
from app.scheduled_jobs.recommendation_ec2_rds import run_ec2_rds_recommendation_scheduler

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=settings.ALLOW_METHODS,
    allow_headers=settings.ALLOW_HEADERS,
)

app.include_router(general.router)
app.include_router(auth.router)
app.include_router(connections.router)
app.include_router(inventory.router)
app.include_router(workspace.router)
app.include_router(recommendation_route.router)
app.include_router(cost_endpoint.router)
app.include_router(terraform.router)
app.include_router(github.router)
app.include_router(existing_to_tf.router)
app.include_router(drift.router)
app.include_router(drift_script_standalone.router)

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

@app.on_event("startup")
async def startup_event():
    start_background_threads()
# app.include_router(websocket.router)
    print("🚀 FastAPI is starting... setting up scheduler.")
    scheduler.add_job(fetch_all_state_files, 'cron', hour=19, minute=45)
    scheduler.add_job(run_cost_scheduler, 'cron', hour=19, minute=45)
    scheduler.add_job(run_daily_drift_detection_job, 'cron', hour=3,minute=0,id="daily_drift_detection",replace_existing=True)
    scheduler.add_job(run_ec2_rds_recommendation_scheduler, 'cron', hour=19, minute=45)

    scheduler.start()
    # print("✅ Scheduler started. The job will run daily at 7:45PM UTC.")
        # 🚀 Run it IMMEDIATELY on startup for testing
    # print("🧪 Running fetch_all_state_files immediately for testing...")
    # fetch_all_state_files()

@app.on_event("shutdown")
def shutdown_scheduler():
    print("🛑 FastAPI is shutting down... stopping scheduler.")
    scheduler.shutdown()
    print("✅ Scheduler shut down cleanly.")