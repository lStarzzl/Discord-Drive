import os
import base64
import asyncio
import discord
import io
import re
import time

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from threading import Thread

BOT_TOKEN = ""
CHANNEL_ID = 
RAW_CHUNK_SIZE = 5400000
STORAGE_MAX_GB = 8

app = Flask(__name__, static_folder='templates')

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
bot_loop = None

RECONSTRUCT_FOLDER = "reconstructed_files"
if not os.path.exists(RECONSTRUCT_FOLDER):
    os.makedirs(RECONSTRUCT_FOLDER)

progress_store = {}

active_uploads = {}

def make_job_id(prefix, name):
    return f"{prefix}_{name}_{int(time.time()*1000)}"

def progress_snapshot(job_id):
    job = progress_store.get(job_id)
    if not job:
        return None
    done    = job["done"]
    total   = job["total"]
    pct     = (done / total * 100) if total > 0 else 0
    elapsed = time.time() - job["started_at"]
    rate    = done / elapsed if elapsed > 0 else 0
    remaining_chunks = total - done
    eta_sec = (remaining_chunks / rate) if rate > 0 else None
    return {
        "label":     job["label"],
        "done":      done,
        "total":     total,
        "pct":       round(pct, 1),
        "eta_sec":   round(eta_sec, 1) if eta_sec is not None else None,
        "finished":  job["finished"],
        "cancelled": job.get("cancelled", False),
        "type":      job["type"],
    }

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]

async def upload_all_chunks(orig_name, chunks, job_id):
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    for b64_data, chunk_name in chunks:
        if progress_store[job_id].get("cancelled"):
            break
        try:
            f = discord.File(fp=io.BytesIO(b64_data.encode('utf-8')), filename=chunk_name)
            await channel.send(content=f"**Node Storage:** `{chunk_name}`", file=f)
        except Exception as e:
            print(f"Upload error: {e}")
        progress_store[job_id]["done"] += 1

    if progress_store[job_id].get("cancelled"):
        async for message in channel.history(limit=500):
            for attachment in message.attachments:
                if attachment.filename.startswith(orig_name + ".") and attachment.filename.endswith(".txt"):
                    await message.delete()
                    await asyncio.sleep(0.3)

    progress_store[job_id]["finished"] = True
    active_uploads.pop(orig_name, None)


async def delete_file_from_discord(target_filename, job_id):
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    to_delete = []
    async for message in channel.history(limit=500):
        for attachment in message.attachments:
            if attachment.filename.startswith(target_filename + ".") and attachment.filename.endswith(".txt"):
                to_delete.append(message)
                break  

    progress_store[job_id]["total"] = len(to_delete) if to_delete else 1

    for message in to_delete:
        await message.delete()
        await asyncio.sleep(0.3)
        progress_store[job_id]["done"] += 1

    progress_store[job_id]["finished"] = True


async def download_and_rebuild(target_filename, job_id):
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    chunk_entries = []
    async for message in channel.history(limit=500):
        for attachment in message.attachments:
            if attachment.filename.startswith(target_filename + ".") and attachment.filename.endswith(".txt"):
                chunk_entries.append((attachment.filename, attachment))

    progress_store[job_id]["total"] = len(chunk_entries) if chunk_entries else 1

    chunks_data = {}
    for fname, attachment in chunk_entries:
        content = await attachment.read()
        chunks_data[fname] = base64.b64decode(content)
        progress_store[job_id]["done"] += 1

    if chunks_data:
        sorted_keys = sorted(chunks_data.keys(), key=natural_sort_key)
        save_path = os.path.join(RECONSTRUCT_FOLDER, target_filename)
        with open(save_path, 'wb') as output_file:
            for key in sorted_keys:
                output_file.write(chunks_data[key])

    progress_store[job_id]["finished"] = True


@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file:
        return "No file selected."

    orig_name   = secure_filename(file.filename)
    file_number = 1
    chunks      = []

    while True:
        chunk = file.read(RAW_CHUNK_SIZE)
        if not chunk:
            break
        b64_data   = base64.b64encode(chunk).decode('utf-8')
        chunk_name = f"{orig_name}.{str(file_number).zfill(6)}.txt"
        chunks.append((b64_data, chunk_name))
        file_number += 1

    job_id = make_job_id("upload", orig_name)
    progress_store[job_id] = {
        "type":       "upload",
        "label":      orig_name,
        "done":       0,
        "total":      len(chunks),
        "started_at": time.time(),
        "finished":   False,
        "cancelled":  False,
    }
    active_uploads[orig_name] = job_id

    if bot_loop:
        asyncio.run_coroutine_threadsafe(upload_all_chunks(orig_name, chunks, job_id), bot_loop)

    return jsonify({"job_id": job_id, "total_chunks": len(chunks)})


@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    if not filename or not bot_loop:
        return "Error"

    upload_job_id = active_uploads.get(filename)
    if upload_job_id and upload_job_id in progress_store:
        progress_store[upload_job_id]["cancelled"] = True

    job_id = make_job_id("delete", filename)
    progress_store[job_id] = {
        "type":       "delete",
        "label":      filename,
        "done":       0,
        "total":      1,   
        "started_at": time.time(),
        "finished":   False,
        "cancelled":  False,
    }

    asyncio.run_coroutine_threadsafe(delete_file_from_discord(filename, job_id), bot_loop)
    return jsonify({"status": "deletion_started", "job_id": job_id})


@app.route('/list-files')
def list_files():
    if not bot_loop:
        return jsonify({"error": "Bot not ready"})

    async def get_stats():
        channel = client.get_channel(CHANNEL_ID)
        files_data  = {}
        total_bytes = 0
        async for msg in channel.history(limit=500):
            for att in msg.attachments:
                total_bytes += att.size
                match = re.match(r"(.+?)\.\d{6}\.txt", att.filename)
                if match:
                    base_name = match.group(1)
                    if base_name not in files_data:
                        files_data[base_name] = {"size": 0}
                    files_data[base_name]["size"] += att.size * 0.75
        return {"files": files_data, "used_bytes": total_bytes}

    future = asyncio.run_coroutine_threadsafe(get_stats(), bot_loop)
    return jsonify(future.result())


@app.route('/reconstruct/<filename>')
def reconstruct(filename):
    if not filename or not bot_loop:
        return "Error"

    job_id = make_job_id("restore", filename)
    progress_store[job_id] = {
        "type":       "restore",
        "label":      filename,
        "done":       0,
        "total":      1,
        "started_at": time.time(),
        "finished":   False,
        "cancelled":  False,
    }

    asyncio.run_coroutine_threadsafe(download_and_rebuild(filename, job_id), bot_loop)
    return jsonify({"job_id": job_id})


@app.route('/progress/<job_id>')
def get_progress(job_id):
    snap = progress_snapshot(job_id)
    if snap is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(snap)


@app.route('/active-jobs')
def active_jobs():
    jobs = []
    for job_id, job in progress_store.items():
        if not job["finished"] and job["type"] in ("delete", "restore"):
            snap = progress_snapshot(job_id)
            snap["job_id"] = job_id
            jobs.append(snap)
    return jsonify(jobs)


@app.route('/')
def index():
    return render_template('index.html')


def run_bot():
    global bot_loop
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    bot_loop.run_until_complete(client.start(BOT_TOKEN))


if __name__ == '__main__':
    Thread(target=run_bot, daemon=True).start()
    app.run(debug=False, port=5000)
