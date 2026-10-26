# Testing and validation report

## Static validation performed in this packaging environment
- Python source files and test files passed `python -m py_compile`.
- The ZIP archive will be checked for integrity and required files before delivery.

## Automated tests included
The backend test suite contains 13 test functions across `backend/tests/`. It covers:
- Login and authentication protection
- Server creation and metric validation
- AI prediction and model-info endpoint
- Failure simulation and successful simulated recovery
- Failed recovery does not mark a service Healthy
- Alert resolution and server deletion
- Settings persistence and invalid threshold rejection
- Monitoring checks and metric history
- HTTP endpoint URL validation and HTTP probe behavior

**Execution status:** The full pytest suite could not be executed in this packaging runtime because Flask and the project dependencies are not installed here, and package installation was unavailable due to network restrictions. Run the tests on the target machine after installing `backend/requirements.txt` with `python -m pytest -q`. Do not treat the included tests as passed until that command succeeds.

## Frontend validation
A production Vite build could not be completed in this packaging environment. The uploaded dependency directory contains Windows-specific native binaries and cannot be used to build on this Linux runtime; network installation was unavailable. The final ZIP excludes `node_modules`. On Windows, run `npm ci` followed by `npm run build` in the `frontend` directory.

## AI evaluation
The model-training script generates `model_metrics.json` from a synthetic dataset. The reported scores measure consistency with synthetic labels only; they do not measure predictive accuracy on real cloud incidents. Regenerate the model and report using `python ml_model.py` after installing backend dependencies.
