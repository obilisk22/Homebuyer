from __future__ import annotations

from pathlib import Path

from nicegui import ui

from app.core.db import UPLOADS_DIR, get_session
from app.core.module_registry import ModuleSpec
from app.core.models import Property
from app.core.property_service import PropertyService


def render(prop: Property, container: ui.element) -> None:
    property_id = prop.id

    with container:
        ui.label("Photos").classes("hb-page-title")
        ui.label(
            "Imported with the listing. Click any photo to expand; pin sets the "
            "library thumbnail."
        ).classes("hb-page-hint")

        status = ui.label("").classes("hb-page-meta q-mt-xs")

        with ui.dialog().props("maximized") as lightbox, ui.card().classes(
            "hb-lightbox w-full h-full items-center justify-center"
        ):
            with ui.row().classes("w-full items-center justify-between q-px-md q-pt-md"):
                lightbox_caption = ui.label("").classes("hb-lightbox-caption")
                ui.button(icon="close", on_click=lightbox.close).classes(
                    "hb-lightbox-close"
                ).props("flat round dense size=sm")
            lightbox_image = (
                ui.image()
                .classes("w-full")
                .style("max-height: calc(100vh - 80px); object-fit: contain;")
            )
            with ui.row().classes("q-gutter-sm q-pa-md"):
                prev_btn = (
                    ui.button(icon="chevron_left")
                    .classes("hb-lightbox-nav")
                    .props("flat round dense size=sm")
                )
                next_btn = (
                    ui.button(icon="chevron_right")
                    .classes("hb-lightbox-nav")
                    .props("flat round dense size=sm")
                )

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

        gallery = ui.element("div").classes("hb-photo-gallery q-mt-sm")

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
                    ui.label(
                        "No photos on file — they import automatically when you "
                        "add a home from Zillow."
                    ).classes("hb-empty-state w-full")
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
                        with ui.element("div").classes("hb-photo-frame"):
                            if abs_path.exists():
                                img = ui.image(src).classes(
                                    "w-full h-full object-cover hb-photo-thumb"
                                )
                                img.on("click", lambda _e=None, i=idx: show_lightbox(i))
                            else:
                                ui.label("Missing file").classes(
                                    "hb-empty-state q-pa-md"
                                )

                            pin_classes = "hb-photo-pin"
                            if is_library_thumb:
                                pin_classes += " hb-photo-pin--active"
                            pin_btn = (
                                ui.button(icon="push_pin")
                                .classes(pin_classes)
                                .props("flat round dense size=sm")
                                .tooltip("Use as library thumbnail")
                            )

                            def set_thumb(pid=photo.id) -> None:
                                try:
                                    with get_session() as session:
                                        PropertyService(session).set_library_thumbnail(
                                            property_id, pid
                                        )
                                    ui.notify(
                                        "Library thumbnail updated", type="positive"
                                    )
                                except ValueError as exc:
                                    ui.notify(str(exc), type="negative")
                                refresh_gallery()

                            pin_btn.on(
                                "click",
                                set_thumb,
                                js_handler="(e) => { e.stopPropagation(); emit(e); }",
                            )

        refresh_gallery(prop)


MODULE = ModuleSpec(id="gallery", title="Photos", order=10, render=render)
