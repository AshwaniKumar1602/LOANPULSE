# LoanPulse — Production Deployment Guide: Render & Neon PostgreSQL

This guide provides step-by-step instructions for deploying **LoanPulse** to [Render](https://render.com) Web Services backed by [Neon](https://neon.tech) Serverless PostgreSQL.

---

## 1. Neon PostgreSQL Database Provisioning

1. Log in to your [Neon Console](https://console.neon.tech).
2. Create a new project:
   - **Project Name**: `loanpulse-db`
   - **Postgres Version**: `16` (or latest recommended)
   - **Region**: Select a region close to your Render deployment (e.g., `Oregon (us-west-2)` or `Frankfurt`).
3. Under the **Dashboard** -> **Connection Details**:
   - Ensure the connection type is set to **Pooled connection** or standard direct connection.
   - Copy the PostgreSQL connection URI.
   - Ensure `sslmode=require` is appended to the connection string:
     ```text
     postgresql://[username]:[password]@[endpoint].neon.tech/loanpulse?sslmode=require
     ```

---

## 2. Deploying to Render Web Services

You can deploy using either **Render Blueprints (IaC)** or via the **Render Web Dashboard**.

### Method A: Automated Deployment via Blueprint (`render.yaml`)

1. Connect your GitHub repository containing LoanPulse to Render.
2. In the Render Dashboard, click **New +** -> **Blueprint**.
3. Select your repository. Render will automatically detect [`render.yaml`](file:///home/ashwa1602/projects/loanpulse/render.yaml).
4. Supply the required environment variables when prompted:
   - `DATABASE_URL`: Your Neon PostgreSQL connection string with `sslmode=require`.
   - `CORS_ALLOWED_ORIGINS`: Your Render URL (e.g., `https://loanpulse.onrender.com`).
5. Click **Apply**. Render will run the automated build command and launch the service.

---

### Method B: Manual Web Service Setup on Render

1. In Render Dashboard, click **New +** -> **Web Service**.
2. Connect your Git repository.
3. Configure the following service settings:
   - **Name**: `loanpulse`
   - **Region**: Same region as Neon (e.g., `Oregon (US West)`)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn -c gunicorn.conf.py wsgi:app`
   - **Instance Type**: `Free` (512MB RAM)

4. Configure the **Environment Variables**:

| Variable | Value / Description |
| :--- | :--- |
| `PYTHON_VERSION` | `3.12.3` |
| `FLASK_APP` | `wsgi.py` |
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `SECRET_KEY` | High-entropy string (min 32 bytes) or click "Generate" |
| `DATABASE_URL` | `postgresql://user:password@endpoint.neon.tech/loanpulse?sslmode=require` |
| `CORS_ALLOWED_ORIGINS` | `https://loanpulse.onrender.com` |
| `GUNICORN_WORKERS` | `2` |
| `GUNICORN_THREADS` | `2` |
| `DB_POOL_SIZE` | `5` |
| `DB_MAX_OVERFLOW` | `2` |
| `DB_POOL_RECYCLE` | `300` |
| `DB_POOL_TIMEOUT` | `30` |
| `SESSION_COOKIE_NAME` | `loanpulse_session` |
| `SESSION_COOKIE_SECURE` | `True` |
| `SESSION_COOKIE_HTTPONLY` | `True` |
| `SESSION_COOKIE_SAMESITE` | `Lax` |
| `PERMANENT_SESSION_LIFETIME` | `7200` |
| `MAX_CONTENT_LENGTH` | `5242880` |

5. Click **Deploy Web Service**.

---

## 3. Initial Production Configuration & Staff Provisioning

The automated build script (`./build.sh`) automatically executes schema migrations (`flask db upgrade`) and seeds the institutional loan products (`flask create-initial-products`).

To provision administrative or officer staff accounts:

1. In Render Dashboard, open the **Shell** tab for the `loanpulse` service.
2. Run the secure interactive CLI command:
   ```bash
   flask create-staff
   ```
3. Enter the corporate email, name, role (`LOAN_OFFICER`, `LOAN_MANAGER`, or `ADMIN`), and password.
4. On the staff member's initial login at `/auth/login`, they will be prompted to configure their Two-Factor Authenticator (TOTP) via QR code.

To verify initial institutional INR products without test users:
```bash
flask create-initial-products
```

---

## 4. Verification & Health Monitoring

1. **System Health Endpoint**:
   Visit: `https://[your-app-name].onrender.com/health`
   Expected response:
   ```json
   {
     "service": "LoanPulse LoanMaster",
     "status": "healthy",
     "version": "1.0.0"
   }
   ```
2. **Product Catalog**:
   Visit: `https://[your-app-name].onrender.com/products` to verify that active institutional loan products are displayed in Indian Rupees (₹ / INR).
3. **Public Landing Page & Persona Selection**:
   Visit: `https://[your-app-name].onrender.com/auth/login` to verify the 3-persona role switcher and single-identity authentication boundary.

---

## 5. Render Free-Tier Memory & Leak Prevention Guidelines

- **Worker Limits**: Gunicorn is configured with `workers=2` and `threads=2` (`gthread` worker class) to keep total memory under 200MB (well beneath Render's 512MB free-tier ceiling).
- **Worker Recycling**: Workers restart after every 1,000 requests (`max_requests=1000`, `max_requests_jitter=50`) to prevent gradual memory bloat.
- **Connection Teardown**: Database sessions are removed via `db.session.remove()` on teardown to prevent connection pool leaks across Neon sleep cycles.
- **Streaming Repayments**: CSV exports use generator streaming to avoid accumulating large result buffers in memory.
