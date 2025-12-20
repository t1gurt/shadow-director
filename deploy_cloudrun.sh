#!/bin/bash

# Configuration
PROJECT_ID="zenn-shadow-director"
SERVICE_NAME="shadow-director-bot"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "Deploying $SERVICE_NAME to Google Cloud Run..."

# 1. Build and Push Container Image
echo "Building and Pushing Docker Image..."
gcloud builds submit --tag $IMAGE_NAME

# 2. Deploy to Cloud Run
# Note: DISCORD_BOT_TOKEN should be set via Secrets Manager in production, 
# but for simplicity/demo we might pass it or expect it to be set in Cloud Run revision.
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars APP_ENV=production,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=True

echo "Deployment Initiated."
