from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid
import tempfile
import logging

# ✅ UTF-8 logging to avoid issues with emojis
logging.basicConfig(level=logging.INFO, format='%(message)s')

app = Flask(__name__)

# ---------- ROUTES ----------

@app.route("/")
def index():
    return render_template("index.html")


# API to get video info
@app.route("/info", methods=["POST"])
def info():
    url = request.form.get("url")
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        ydl_opts = {"quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)

        formats = []
        allowed_resolutions = {"240p", "480p", "720p", "1080p", "1440p", "2160p"}

        def normalize_resolution(res):
            if not res:
                return None
            res = res.lower()
            if "720" in res: return "720p"
            if "1080" in res: return "1080p"
            if "1440" in res: return "1440p"
            if "2160" in res or "4k" in res: return "2160p"
            if "480" in res: return "480p"
            if "240" in res: return "240p"
            return None

        best_by_res = {}

        for f in info_dict.get("formats", []):
            raw_res = f.get("resolution") or f.get("format_note")
            resolution = normalize_resolution(raw_res)
            if not resolution or resolution not in allowed_resolutions:
                continue

            if f.get("vcodec") != "none":
                stream_type = "video+audio" if f.get("acodec") != "none" else "video-only"
                if f.get("filesize"):
                    size_mb = round(f["filesize"] / (1024 * 1024), 2)
                elif f.get("filesize_approx"):
                    size_mb = round(f["filesize_approx"] / (1024 * 1024), 2)
                else:
                    size_mb = None

                if resolution not in best_by_res:
                    best_by_res[resolution] = {
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "resolution": resolution,
                        "filesize": size_mb,
                        "stream_type": stream_type,
                    }
                else:
                    old = best_by_res[resolution]
                    if size_mb and (not old["filesize"] or size_mb > old["filesize"]):
                        best_by_res[resolution] = {
                            "format_id": f.get("format_id"),
                            "ext": f.get("ext"),
                            "resolution": resolution,
                            "filesize": size_mb,
                            "stream_type": stream_type,
                        }

        resolution_order = {"240p": 1, "480p": 2, "720p": 3, "1080p": 4, "1440p": 5, "2160p": 6}
        formats = sorted(best_by_res.values(), key=lambda x: resolution_order.get(x["resolution"], 999))

        return jsonify({
            "title": info_dict.get("title"),
            "thumbnail": info_dict.get("thumbnail"),
            "formats": formats
        })

    except Exception as e:
        logging.error("yt-dlp info error: %s", str(e))
        return jsonify({"error": str(e)}), 500


# Download route (uses temporary files for Render)
@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    format_id = request.form.get("format_id")
    stream_type = request.form.get("stream_type")

    if not url or not format_id:
        return "Missing data", 400

    # Use temporary file (avoids Render ephemeral storage issues)
    suffix = ".mp4" if stream_type != "audio-only" else ".m4a"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
        output_path = tmp_file.name

    try:
        ydl_opts = {
            "outtmpl": output_path,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True
        }

        if stream_type == "video-only":
            ydl_opts["format"] = f"{format_id}+bestaudio/best"
        elif stream_type == "video+audio":
            ydl_opts["format"] = format_id
        elif stream_type == "audio-only":
            ydl_opts["format"] = format_id
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"

        logging.info("Downloading %s", url)
        logging.info("Format: %s", ydl_opts["format"])
        logging.info("Output: %s", output_path)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(output_path, as_attachment=True, download_name=os.path.basename(output_path))

    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
