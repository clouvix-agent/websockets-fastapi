# Chatbot Server

A simple FastAPI server for chatbot functionality.

## Project Structure
```
app/
├── core/           # Core application configuration
│   ├── __init__.py
│   └── config.py
├── models/         # Data models and schemas
│   └── __init__.py
├── routers/        # API route handlers
│   ├── __init__.py
│   └── general.py
├── __init__.py
└── main.py        # Main application entry point
```

## Setup

1. Make sure you have Python 3.7+ installed
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

To run the server, use the following command:

```bash
uvicorn app.main:app --reload
```

The server will start at `http://localhost:8000`

## Available Endpoints

- `GET /`: Welcome message
- `GET /hello`: Hello endpoint that returns a greeting message

## API Documentation

Once the server is running, you can access:
- Swagger UI documentation at: `http://localhost:8000/docs`
- ReDoc documentation at: `http://localhost:8000/redoc` 