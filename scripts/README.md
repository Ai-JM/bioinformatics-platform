# scripts

This directory is reserved for executable analysis scripts.

Recommended conventions:

- Keep each pipeline step as a standalone script with CLI arguments.
- Write outputs only to the `--outdir` path passed by the Streamlit app.
- Preserve machine-readable tables next to generated figures.
- Keep R scripts Docker-friendly by avoiding hard-coded local paths.
