# Deployment requirements (identified in Sprint II, for Sprint III)

Target hosting: Cloudflare or AWS (to be confirmed with the supervisor).

| Need | Why | Options |
|---|---|---|
| Run the FastAPI app (long-running Python process) | The API holds the model in memory and talks to PostgreSQL | AWS App Runner, ECS Fargate or Lightsail. Cloudflare Workers do not run this Python and XGBoost stack as is, so Cloudflare would sit in front (DNS, TLS, access control) rather than host it |
| Managed PostgreSQL | Replace the local database | AWS RDS PostgreSQL (smallest size is enough for the synthetic data) |
| Model file delivery | `models/xgb_final_v1.pkl` is not in Git | Bake into the container image, or store in S3 and download at start |
| Secrets | DATABASE_URL now, auth keys later | Host secret store or environment variables, never committed |
| HTTPS and access control | Dashboard has no login yet | TLS from the host or Cloudflare; Cloudflare Access as a stop-gap until FR-01 is built |
| Container image | Reproducible deploys | Dockerfile: python:3.12-slim, `pip install -r requirements.txt`, `uvicorn api.main:app --host 0.0.0.0` |
| CI/CD | Deploy after tests pass | Extend `.github/workflows/ci.yml` with a build and deploy job |
| Backend URL for the mobile app | Kotlin app must reach the API | Stable HTTPS URL, CORS configured for the app |
| Monitoring | Know when it is down | `/health` already reports model and database status; point an uptime check at it |
| Cost | Student budget | One small instance plus smallest RDS size; stop when not demoing |

Open decision for the supervisor: everything on AWS, or AWS compute with Cloudflare in front.
