from __future__ import annotations

from pathlib import Path

from nicegui import events, ui

from app.core.db import UPLOADS_DIR, get_session
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id

    with container:
        ui.label("Photos").classes("text-h6")
        ui.label("Auto-imported from the Zillow listing. Click any photo to expand.").classes(
            "text-caption text-grey-7"
        )

        status = ui.label("").classes("text-body2 text-grey-6 q-mt-xs")
        gallery = ui.element("div").classes("hb-photo-gallery q-mt-sm")

        with ui.dialog().props("maximized") as lightbox, ui.card().classes(
            "w-full h-full bg-black text-white items-center justify-center"
        ):
            with ui.row().classes("w-full items-center justify-between q-px-md q-pt-md"):
                lightbox_caption = ui.label("").classes("text-subtitle1")
                ui.button(icon="close", on_click=lightbox.close).props(
                    "flat round dense color=white"
                )
            lightbox_image = (
                ui.image()
                .classes("w-full")
                .style("max-height: calc(100vh - 80px); object-fit: contain;")
            )
            with ui.row().classes("q-gutter-sm q-pa-md"):
                prev_btn = ui.button(icon="chevron_left").props("flat round color=white")
                next_btn = ui.button(icon="chevron_right").props("flat round color=white")

        photo_urls: list[str] = []
        photo_captions: list[str] = []
        current_index = {"value": 0}

        def show_lightbox(index: int) -> None:
            if not photo_urls:
                return
            current_index["value"] = index % len(photo_urls)
            i = current_index["value"]
            lightbox_image.set_source(photo_urls[i])
            lightbox_caption.set_text(
                f"{photo_captions[i]}  ({i + 1} / {len(photo_urls)})"
            )
            lightbox.open()

        prev_btn.on_click(lambda: show_lightbox(current_index["value"] - 1))
        next_btn.on_click(lambda: show_lightbox(current_index["value"] + 1))

        def refresh_gallery(initial: Property | None = None) -> None:
            gallery.clear()
            photo_urls.clear()
            photo_captions.clear()
            thumb_id: int | None = None
            if initial is not None:
                photos = list(initial.photos)
                thumb_id = initial.thumbnail_photo_id
            else:
                with get_session() as session:
                    fresh = PropertyService(session).get_property(property_id)
                    photos = list(fresh.photos) if fresh else []
                    thumb_id = fresh.thumbnail_photo_id if fresh else None

            status.set_text(f"{len(photos)} photo{'s' if len(photos) != 1 else ''}")

            with gallery:
                if not photos:
                    ui.label("No photos yet — import from Zillow or upload manually.").classes(
                        "text-grey-6"
                    )
                    return

                for idx, photo in enumerate(photos):
                    abs_path = UPLOADS_DIR / photo.path
                    src = f"/uploads/{photo.path}"
                    caption = photo.caption or Path(photo.path).name
                    photo_urls.append(src)
                    photo_captions.append(caption)
                    is_library_thumb = thumb_id is not None and photo.id == thumb_id
                    card_classes = "hb-photo-card cursor-pointer overflow-hidden"
                    if is_library_thumb:
                        card_classes += " hb-photo-card--library-thumb"

                    with ui.card().tight().classes(card_classes):
                        if abs_path.exists():
                            img = ui.image(src).classes(
                                "w-full h-full object-cover hb-photo-thumb"
                            )
                            img.on("click", lambda _e=None, i=idx: show_lightbox(i))
                        else:
                            ui.label("Missing file").classes("q-pa-md")
                        with ui.card_section().classes("q-pa-xs"):
                            with ui.row().classes(
                                "w-full items-center justify-between gap-1 no-wrap"
                            ):
                                label_bits = caption
                                if is_library_thumb:
                                    label_bits = f"{caption} · Library thumb"
                                ui.label(label_bits).classes("text-caption ellipsis")
                                pin_btn = ui.button(icon="push_pin").props(
                                    "flat round dense size=sm color=primary"
                                ).tooltip("Use as library thumbnail")

                                def set_thumb(pid=photo.id) -> None:
                                    try:
                                        with get_session() as session:
                                            PropertyService(session).set_library_thumbnail(
                                                property_id, pid
                                            )
                                        ui.notify("Library thumbnail updated", type="positive")
                                    except ValueError as exc:
                                        ui.notify(str(exc), type="negative")
                                    refresh_gallery()

                                pin_btn.on(
                                    "click",
                                    set_thumb,
                                    js_handler="(e) => { e.stopPropagation(); emit(e); }",
                                )

        def import_from_zillow(replace: bool = False) -> None:
            try:
                with get_session() as session:
                    count = PropertyService(session).import_zillow_photos(
                        property_id, replace=replace
                    )
                if count:
                    ui.notify(f"Imported {count} photos from Zillow", type="positive")
                else:
                    ui.notify("No new photos found (already imported?)", type="info")
            except ValueError as exc:
                ui.notify(str(exc), type="negative")
            except Exception as exc:  # noqa: BLE001 — surface import failures in UI
                ui.notify(f"Import failed: {exc}", type="negative")
            refresh_gallery()

        def auto_pick_again() -> None:
            try:
                with get_session() as session:
                    PropertyService(session).unlock_and_select_thumbnail(property_id)
                ui.notify("Auto-picked a new library thumbnail", type="positive")
            except ValueError as exc:
                ui.notify(str(exc), type="negative")
            refresh_gallery()

        async def handle_upload(e: events.UploadEventArguments) -> None:
            upload_dir = UPLOADS_DIR / "_tmp"
            upload_dir.mkdir(parents=True, exist_ok=True)
            name = e.file.name or "upload.bin"
            tmp = upload_dir / name
            await e.file.save(tmp)
            with get_session() as session:
                PropertyService(session).add_photo(property_id, tmp, caption=name)
            tmp.unlink(missing_ok=True)
            ui.notify("Photo added", type="positive")
            refresh_gallery()

        with ui.row().classes("q-mt-sm gap-2 flex-wrap"):
            ui.button(
                "Import from Zillow",
                on_click=lambda: import_from_zillow(False),
                icon="cloud_download",
            ).props("color=primary")
            ui.button(
                "Re-import (replace)",
                on_click=lambda: import_from_zillow(True),
                icon="refresh",
            ).props("outline color=primary")
            ui.button(
                "Auto-pick again",
                on_click=auto_pick_again,
                icon="auto_awesome",
            ).props("outline color=primary")

        ui.upload(
            label="Or upload photos",
            on_upload=handle_upload,
            auto_upload=True,
            multiple=True,
        ).props('accept="image/*"').classes("q-mt-sm")

        refresh_gallery(prop)


MODULE = ModuleSpec(id="gallery", title="Photos", order=10, render=render)
