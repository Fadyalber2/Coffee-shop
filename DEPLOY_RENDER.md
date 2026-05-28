# Deploy Cozy Coffee on Render

1. Push this project to GitHub.
2. In Render, choose **Web Services** then **New Web Service**.
3. Connect the GitHub repository.
4. Use these settings:
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn wsgi:app`
5. Add environment variables:
   - `STRIPE_SECRET_KEY`: your Stripe secret key
   - `STRIPE_CURRENCY`: `usd`
6. Click **Deploy Web Service**.

The Flask backend serves the frontend templates, so one Render Web Service deploys both frontend and backend together.
