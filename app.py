from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid

app = Flask(__name__)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

# ✅ API to get video info (preview + formats)
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

                # Only keep video formats
                if f.get("vcodec") != "none":
                    stream_type = "video+audio" if f.get("acodec") != "none" else "video-only"

                    # File size
                    if f.get("filesize"):
                        size_mb = round(f["filesize"] / (1024 * 1024), 2)
                    elif f.get("filesize_approx"):
                        size_mb = round(f["filesize_approx"] / (1024 * 1024), 2)
                    else:
                        size_mb = None

                    # Keep best per resolution
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

            # Sort in resolution order
            resolution_order = {"240p": 1, "480p": 2, "720p": 3, "1080p": 4, "1440p": 5, "2160p": 6}
            formats = sorted(best_by_res.values(), key=lambda x: resolution_order.get(x["resolution"], 999))

            return jsonify({
                "title": info_dict.get("title"),
                "thumbnail": info_dict.get("thumbnail"),
                "formats": formats
            })
    except Exception as e:
        print(" yt-dlp info error:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    format_id = request.form.get("format_id")
    stream_type = request.form.get("stream_type")
    if not url or not format_id:
        return "Missing data", 400

    # always force mp4 output unless audio-only
    output_path = os.path.join("downloads", f"{uuid.uuid4()}.mp4")
    try:
        ydl_opts = {
            "outtmpl": output_path,  # ✅ exact filename
            "merge_output_format": "mp4",  # ✅ ensures merge container is mp4
            "noplaylist": True,
            "quiet": False,
            "verbose": True,
        }

        # ✅ choose format correctly
        if stream_type == "video-only":
            ydl_opts["format"] = f"{format_id}+bestaudio/best"
        elif stream_type == "video+audio":
            ydl_opts["format"] = format_id
        elif stream_type == "audio-only":
            output_path = output_path.replace(".mp4", ".m4a")
            ydl_opts["outtmpl"] = output_path
            ydl_opts["format"] = format_id
        else:
            ydl_opts["format"] = "bestvideo+bestaudio/best"

        print(f" Downloading {url}")
        print(f" Format: {ydl_opts['format']}")
        print(f" Output: {output_path}")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # ✅ check file exists before sending
        if not os.path.exists(output_path):
            return f"File not found after download: {output_path}", 500

        return send_file(output_path, as_attachment=True, download_name=os.path.basename(output_path))

    except Exception as e:
        print(" yt-dlp error:", str(e))
        return str(e), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
