.PHONY: help dev-api dev-web install deploy deploy-api deploy-web logs logs-tail console status secrets

help:
	@echo "Audit Bureau — commandes principales"
	@echo ""
	@echo "  make install       → npm install + pip install (venv local)"
	@echo "  make dev-api       → backend FastAPI en dev (port 8000)"
	@echo "  make dev-web       → frontend Next.js en dev (port 3001)"
	@echo ""
	@echo "Déploiement Fly.io (backend) :"
	@echo "  make deploy-api    → fly deploy"
	@echo "  make logs          → logs live du backend"
	@echo "  make status        → statut des machines Fly"
	@echo "  make secrets       → liste des secrets Fly (masqués)"
	@echo "  make console       → SSH dans une machine Fly"
	@echo ""
	@echo "Déploiement Vercel (frontend) :"
	@echo "  make deploy-web    → vercel --prod"

install:
	npm install
	/tmp/audit-venv/bin/pip install -r api/requirements.txt

dev-api:
	SEED_FIXTURE=1 /tmp/audit-venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --log-level info --reload

dev-web:
	npx next dev --port 3001

deploy: deploy-api deploy-web

deploy-api:
	fly deploy --remote-only

deploy-web:
	cd . && vercel --prod

logs:
	fly logs -a audit-bureau-api

logs-tail:
	fly logs -a audit-bureau-api -i

status:
	fly status -a audit-bureau-api

secrets:
	fly secrets list -a audit-bureau-api

console:
	fly ssh console -a audit-bureau-api
