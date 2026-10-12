"""One-photo plant overview using both local image models."""
import hashlib

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as FormUploadFile

from .fruit_vision import assess_fruit_image, normalize_species
from .plant_vision import assess_image, MAX_IMAGE_BYTES, SUPPORTED_SPECIES
from .plant_overview import build_overview, curate_with_gemini, gemini_status, recalled, remember

router = APIRouter(prefix="/api")


@router.get("/plant-overview/status")
def status():
    return {"ai": gemini_status(), "local_summary_available": True}


@router.post("/plant-overview")
async def screen_plant(request: Request, file: UploadFile = File(...),
        crop_species: str = Form("tomato"), plant_id: str = Form("Plant 01"),
        fruit_model_id: str | None = Form(None)):
    uploads = [value for _, value in (await request.form()).multi_items()
               if isinstance(value, FormUploadFile)]
    try:
        species = normalize_species(crop_species)
        if species not in SUPPORTED_SPECIES:
            raise HTTPException(422, "Combined screening supports tomato, potato and bell pepper.")
        model_id = fruit_model_id or ("tomato-ripeness-3" if species == "tomato" else "produce-detection")
        if not isinstance(plant_id, str) or not plant_id.strip() or len(plant_id) > 64 or any(ord(c) < 32 for c in plant_id):
            raise HTTPException(422, "Use a plant label of 1–64 printable characters.")
        if len(uploads) != 1:
            raise HTTPException(422, "Upload exactly one plant photograph; both analyses use that same image.")
        image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Keep the plant photograph within 10 MiB.")
        if not image_bytes:
            raise HTTPException(422, "The uploaded photograph is empty.")
        leaf = await run_in_threadpool(assess_image, image_bytes, species)
        fruit = await run_in_threadpool(assess_fruit_image, image_bytes, species, model_id)
        overview = build_overview(species, leaf, fruit, single_photo=True)
        return {"schema_version": 2, "plant_id": plant_id.strip(), "crop_species": species,
            "input_mode": "single_photo", "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "leaf": leaf, "fruit": fruit, "overview": overview, "evidence_id": remember(overview),
            "ai": gemini_status(), "images_uploaded_to_provider": False, "automatic_action": False}
    finally:
        for upload in uploads:
            await upload.close()


@router.post("/plant-overview/ai")
async def ai_summary(payload: dict = Body(...)):
    try:
        overview = recalled(payload.get("evidence_id"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return await run_in_threadpool(curate_with_gemini, overview)
