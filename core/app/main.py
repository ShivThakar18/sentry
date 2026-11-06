from fastapi import FastAPI

app = FastAPI(title="SENTRY Core")          # the AGIS app object 

@app.get("/health")
async def health():
    return {"ok", True}                     # FastAPI turns a retruned dict into JSON automatically



