`````md path="README.md"
# MSDS Generation Backend

## Overview

This repository contains a Flask‑based backend service that generates Material Safety Data Sheets (MSDS/SDS) for chemical compounds given a SMILES string.  
Key features:

- **SMILES validation** using RDKit.
- **Full 16‑section SDS generation** with data sourced from PubChem, RDKit, and computational predictions.
- **Export options**:
  - JSON response via `/api/sds`
  - Downloadable Word document (`.docx`) via `/api/sds/docx`
  - Downloadable JSON file via `/api/sds/json`
- **Section‑by‑section access** via `/api/sds/section/<section_num>`.
- **Health check** endpoint with RDKit status.

The service is containerised with Docker and ready for deployment on platforms like Render, Fly.io, or any Docker‑compatible host.

## Repository Structure

```
backend/
├── Dockerfile                 # Build image with Conda, RDKit, wkhtmltopdf, and Python deps
├── docker-compose.yml         # Local development stack (backend + optional Nginx)
├── requirements.txt           # Python dependencies
├── main.py                    # Flask app, routes, logging, and startup logic
├── sds_generator.py           # Core SDS generation logic (not shown here)
├── sds_data_fetcher.py        # Helper functions for external data (PubChem, etc.)
└── __pycache__/               # Compiled Python files (auto‑generated)
```

## Quick Start (Docker)

### Prerequisites

- Docker Engine (>=20.10)
- (Optional) Docker Compose for local multi‑service testing

### Build & Run

```bash
# Clone the repo
git clone https://github.com/AdityaPanda0506/MSDS-Generation.git
cd MSDS-Generation/backend

# Build the Docker image
docker build -t msds-backend .

# Run the container (exposes port 5000)
docker run -d -p 5000:5000 --name msds-backend msds-backend
```

The API will be reachable at `http://localhost:5000`.

### Using Docker Compose (incl. optional Nginx)

```bash
docker compose up -d
```

- Backend: `http://localhost:5000`
- Nginx (if enabled via `profiles: production`): `http://localhost` (port 80/443)

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check, RDKit status, available endpoints |
| `/api/validate` | POST | Validate SMILES, return canonical SMILES, formula, weight |
| `/api/sections` | GET | List the 16 SDS section names |
| `/api/sds` | GET/POST | Generate full SDS JSON (body or query param `smiles`) |
| `/api/sds/docx` | GET/POST | Download SDS as a Word document |
| `/api/sds/json` | GET/POST | Download SDS as a JSON file |
| `/api/sds/section/<int:section_num>` | GET | Retrieve a single SDS section (1‑16) |
| `*` (any other) | – | Returns 404 with list of available endpoints |

### Request Parameters

- **`smiles`** – SMILES string of the compound.  
  - For `GET` requests: query parameter `?smiles=...`  
  - For `POST` requests: JSON body `{ "smiles": "C(C)O" }`

### Example: Validate a SMILES string

```bash
curl -X POST http://localhost:5000/api/validate \
     -H "Content-Type: application/json" \
     -d '{"smiles":"CCO"}'
```

Response:

```json
{
  "valid": true,
  "smiles": "CCO",
  "molecular_formula": "C2H6O",
  "molecular_weight": 46.07,
  "message": "SMILES is valid and ready for SDS generation"
}
```

## Development

### Local Python Environment (without Docker)

```bash
# Create a Conda env (RDKit requires Conda)
conda create -n msds python=3.12 -y
conda activate msds
conda install -c conda-forge rdkit -y

# Install pip deps
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Run the app
export FLASK_APP=main.py
flask run --host=0.0.0.0 --port=5000
```

### Environment Variables

- `PORT` – Port for the Flask app (defaults to `5000`).
- `.env` file can be used for future secrets (e.g., API keys for external services).

## Production Tips

1. **Upgrade pip, setuptools, wheel** – The Dockerfile does this before installing other packages (prevents known import errors).
2. **Use gunicorn** – The container runs with 2 workers and a 120 s timeout.
3. **Health checks** – Docker‑compose includes a health‑check that curls `/api/health`.
4. **Static assets** – If you add a React front‑end, serve it via the optional Nginx container.
5. **Logging** – Structured logs are emitted to `stdout`; configure a log driver or external logging service as needed.

## License

This project is provided under the MIT License. See the `LICENSE` file for details.

---  

*For any questions or contributions, feel free to open an issue or submit a pull request.*
