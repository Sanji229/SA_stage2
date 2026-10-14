import streamlit as st
from PIL import Image, UnidentifiedImageError

MAX_PHOTOS = 12


@st.dialog("Capture or upload photos")
def add_photos_dialog():
    st.write("Add classroom photos to scan for attendance. Photos stay in memory and are never saved.")
    images = st.session_state.attendance_images
    mode = st.segmented_control("Source", ["Upload", "Camera"], default="Upload", key="photo_source")

    if mode == "Camera":
        cam = st.camera_input("Take a snapshot", key="dialog_cam")
        if cam and st.button("Add this photo", type="primary"):
            images.append(Image.open(cam).copy())
            st.rerun()
    else:
        files = st.file_uploader("Choose image files", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="dialog_upload")
        if files and st.button(f"Add {len(files)} photo(s)", type="primary"):
            bad = 0
            for f in files:
                if len(images) >= MAX_PHOTOS:
                    st.warning(f"Limit of {MAX_PHOTOS} photos per session reached.")
                    break
                try:
                    images.append(Image.open(f).copy())
                except (UnidentifiedImageError, OSError):
                    bad += 1
            if bad:
                st.session_state.flash_warn = f"{bad} file(s) could not be read as images and were skipped."
            st.rerun()

    st.caption(f"{len(images)} photo(s) added")
    if st.button("Done", width="stretch"):
        st.rerun()
