FROM python:3.12-slim

# Hugging Face Spaces runs containers as user 1000, so own everything from the start.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    TORCH_HOME=/home/user/.cache/torch \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /home/user/app

# CPU-only torch first: the default Linux wheels bundle several GB of CUDA.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchvision==0.19.1
COPY --chown=user requirements.txt .
RUN pip install -r requirements.txt

# Weights are baked in at build time. Only the code they need is copied first, so editing the
# frontend or server doesn't download them again.
COPY --chown=user models.py registry.py metrics.py cartoongan.py classic_filter.py weight_store.py ./
COPY --chown=user tools/download_weights.py tools/
RUN python tools/download_weights.py

COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
