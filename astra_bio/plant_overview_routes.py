"""Local plant overview, with an optional leaf close-up for leaf classification."""
import hashlib

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as FormUploadFile

from .fruit_vision import assess_fruit_image, normalize_species
from .plant_vision import assess_image, model_status, MAX_IMAGE_BYTES, SUPPORTED_SPECIES
from .plant_overview import build_overview, curate_with_gemini, gemini_status, recalled, remember

router = APIRouter(prefix="/api")


@router.get("/plant-overview/status")
def status():
    return {"ai": gemini_status(), "leaf_model": model_status(), "local_summary_available": True}


@router.post("/plant-overview")
async def screen_plant(request: Request, file: UploadFile = File(...),
        crop_species: str = Form("tomato"), plant_id: str = Form("Plant 01"),
        fruit_model_id: str | None = Form(None), leaf_file: UploadFile | None = File(None),
        screening_mode: str = Form("combined")):
    uploads = [(key, value) for key, value in (await request.form()).multi_items()
               if isinstance(value, FormUploadFile)]
    try:
        if screening_mode not in {"combined", "leaf", "fruit"}:
            raise HTTPException(422, "Screening mode must be combined, leaf or fruit.")
        species = normalize_species(crop_species)
        if species not in SUPPORTED_SPECIES:
            raise HTTPException(422, "Combined screening supports tomato, potato and bell pepper.")
        model_id = fruit_model_id or ("tomato-ripeness-3" if species == "tomato" else "produce-detection")
        if not isinstance(plant_id, str) or not plant_id.strip() or len(plant_id) > 64 or any(ord(c) < 32 for c in plant_id):
            raise HTTPException(422, "Use a plant label of 1–64 printable characters.")
        upload_keys = [key for key, _ in uploads]
        if upload_keys.count("file") != 1 or upload_keys.count("leaf_file") > 1 or any(key not in {"file", "leaf_file"} for key in upload_keys):
            raise HTTPException(422, "Upload exactly one photograph and at most one optional leaf close-up.")
        if screening_mode != "combined" and upload_keys.count("leaf_file"):
            raise HTTPException(422, "Single-purpose screening accepts one photograph; remove the extra leaf image.")
        image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Keep the photograph within 10 MiB.")
        if not image_bytes:
            raise HTTPException(422, "The uploaded photograph is empty.")
        leaf_bytes = image_bytes
        if screening_mode == "combined" and leaf_file is not None:
            leaf_bytes = await leaf_file.read(MAX_IMAGE_BYTES + 1)
            if len(leaf_bytes) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "Keep the leaf close-up within 10 MiB.")
            if not leaf_bytes:
                raise HTTPException(422, "The uploaded leaf close-up is empty.")
        leaf_source = "leaf_closeup" if screening_mode == "combined" and leaf_file is not None else "leaf_photo" if screening_mode == "leaf" else "plant_photo"
        if screening_mode in {"combined", "leaf"}:
            leaf = {**await run_in_threadpool(assess_image, leaf_bytes, species), "input_source": leaf_source}
        else:
            leaf = {"status": "not_requested", "reason": "Leaf screening was not requested in fruit-checking mode.", "predictions": [], "input_source": "not_requested"}
        if screening_mode in {"combined", "fruit"}:
            fruit = await run_in_threadpool(assess_fruit_image, image_bytes, species, model_id)
        else:
            fruit = {"status": "not_requested", "reason": "Fruit checking was not requested in leaf-screening mode.", "detections": [], "visible_count": None, "counts_by_stage": {}}
        overview = build_overview(species, leaf, fruit, single_photo=screening_mode == "combined" and leaf_file is None) if screening_mode == "combined" else None
        evidence_id = remember(overview) if overview is not None else None
        return {"schema_version": 3, "screening_mode": screening_mode, "plant_id": plant_id.strip(), "crop_species": species,
            "input_mode": "plant_photo_with_leaf_closeup" if screening_mode == "combined" and leaf_file is not None else "single_photo",
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "leaf_image_sha256": hashlib.sha256(leaf_bytes).hexdigest() if screening_mode in {"combined", "leaf"} else None,
            "leaf_input_source": leaf_source, "leaf": leaf, "fruit": fruit, "overview": overview, "evidence_id": evidence_id,
            "ai": gemini_status(), "images_uploaded_to_provider": False, "automatic_action": False}
    finally:
        for _, upload in uploads:
            await upload.close()


@router.post("/plant-overview/ai")
async def ai_summary(payload: dict = Body(...)):
    try:
        overview = recalled(payload.get("evidence_id"))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return await run_in_threadpool(curate_with_gemini, overview)
