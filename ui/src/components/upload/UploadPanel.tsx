"use client";

import { type FormEvent, useRef, useState } from "react";
import { Upload, FileText, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { getIngestionStatus, uploadDocument } from "../../lib/api";
import { cn } from "../../lib/utils";

const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;
type UploadState = "idle" | "uploading" | "processing" | "success" | "error";

export function UploadPanel() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>("idle");
  const [message, setMessage] = useState("");

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setState("error");
      setMessage("File exceeds the 25 MB upload limit.");
      return;
    }
    setFile(f);
    setState("idle");
    setMessage("");
  }

  async function waitForIngestion(jobId: string) {
    for (let attempts = 0; attempts < 120; attempts += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1_000));
      const job = await getIngestionStatus(jobId);
      setMessage(`${job.message} (${job.progress}%)`);
      if (job.status === "completed") {
        setState("success");
        return;
      }
      if (job.status === "failed") {
        setState("error");
        return;
      }
    }
    setState("error");
    setMessage("Ingestion is taking longer than expected. Please check back later.");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;

    setState("uploading");
    setMessage("");

    try {
      const job = await uploadDocument(file);
      setState("processing");
      setMessage(`${job.message} (${job.progress}%)`);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      await waitForIngestion(job.job_id);
    } catch {
      setState("error");
      setMessage("Upload failed. Please verify the file and try again.");
    }
  }

  const isBusy = state === "uploading" || state === "processing";

  return (
    <div className="border-t border-zinc-800 p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Upload Document
      </h3>

      <form onSubmit={handleSubmit} className="space-y-3">
        <label
          htmlFor="file-upload"
          className={cn(
            "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 transition-colors",
            file ? "border-blue-500/50 bg-blue-500/5" : "border-zinc-700 hover:border-zinc-500",
          )}
        >
          {file ? <FileText className="h-6 w-6 text-blue-400" /> : <Upload className="h-6 w-6 text-zinc-500" />}
          <span className="text-xs text-zinc-400">{file ? file.name : "Click to select a file"}</span>
          {file && <span className="text-[10px] text-zinc-500">{(file.size / 1024).toFixed(1)} KB</span>}
          <input
            ref={inputRef}
            id="file-upload"
            type="file"
            accept=".pdf,.html,.htm,.txt,.docx,.pptx"
            className="hidden"
            onChange={handleFileSelect}
            disabled={isBusy}
          />
        </label>

        <button
          type="submit"
          disabled={!file || isBusy}
          className={cn(
            "flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors",
            "bg-blue-600 text-white hover:bg-blue-700",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {isBusy ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />{state === "uploading" ? "Uploading..." : "Ingesting..."}</> : "Ingest into Knowledge Base"}
        </button>
      </form>

      {state === "success" && <div className="mt-2 flex items-center gap-1.5 rounded bg-green-900/30 px-3 py-2"><CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-400" /><span className="text-xs text-green-300">{message}</span></div>}
      {state === "error" && <div className="mt-2 flex items-center gap-1.5 rounded bg-red-900/30 px-3 py-2"><XCircle className="h-3.5 w-3.5 shrink-0 text-red-400" /><span className="text-xs text-red-300">{message}</span></div>}
    </div>
  );
}
