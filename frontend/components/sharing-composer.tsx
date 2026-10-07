"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import type { LocalParticipant } from "livekit-client";
import { ArrowUp, FileText, LoaderCircle, Paperclip, X } from "lucide-react";
import {
  ACCEPT_FILES,
  MAX_FILES,
  sendAttachments,
  validateFiles,
  type AttachmentBatch,
} from "../lib/attachments";

export type SharedMessage = {
  id: string;
  timestamp: number;
  message: string;
  files: { name: string; preview?: string }[];
};
export default function SharingComposer({
  participant,
  destination,
  ready,
  draft,
  setDraft,
  inputRef,
  onText,
  onShared,
  onError,
  sessionKey,
  incomingFiles,
  onSent,
}: {
  participant: LocalParticipant;
  destination?: string;
  ready: boolean;
  draft: string;
  setDraft: (text: string) => void;
  inputRef: RefObject<HTMLInputElement | null>;
  onText: (text: string) => Promise<void>;
  onShared: (message: SharedMessage) => void;
  onError: (text: string) => void;
  sessionKey: boolean;
  incomingFiles?: File[];
  onSent?: () => void;
}) {
  const [files, setFiles] = useState<{ file: File; preview?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const batch = useRef<AttachmentBatch | null>(null);
  const previews = useRef(new Set<string>());
  const generation = useRef(0);
  const sending = useRef(false);

  useEffect(() => {
    generation.current++;
    if (sessionKey) {
      const staged = new Set(files.map((file) => file.preview));
      for (const url of previews.current)
        if (!staged.has(url)) {
          URL.revokeObjectURL(url);
          previews.current.delete(url);
        }
    }
    batch.current = null;
    setUncertain(false);
    setBusy(false);
    sending.current = false;
  }, [sessionKey]);
  useEffect(
    () => () => {
      for (const url of previews.current) URL.revokeObjectURL(url);
    },
    [],
  );
  function add(incoming: File[]) {
    if (busy || uncertain) return;
    try {
      validateFiles(incoming, files.length);
      setFiles((current) => [
        ...current,
        ...incoming.map((file) => {
          const preview = /\.(png|jpe?g|webp|gif)$/i.test(file.name)
            ? URL.createObjectURL(file)
            : undefined;
          if (preview) previews.current.add(preview);
          return { file, preview };
        }),
      ]);
      batch.current = null;
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Could not attach files.",
      );
    }
  }
  useEffect(() => {
    if (incomingFiles?.length) add(incomingFiles);
  }, [incomingFiles]);
  function remove(index: number) {
    const url = files[index].preview;
    if (url) {
      URL.revokeObjectURL(url);
      previews.current.delete(url);
    }
    setFiles((current) => current.filter((_, i) => i !== index));
    batch.current = null;
  }
  async function submit() {
    if (!ready || sending.current || (!draft.trim() && !files.length)) return;
    sending.current = true;
    setBusy(true);
    onError("");
    const currentGeneration = generation.current;
    try {
      if (files.length && destination) {
        batch.current ??= {
          requestId: crypto.randomUUID(),
          files: files.map((item) => item.file),
          question: draft.trim(),
          ids: [],
          committing: false,
        };
        await sendAttachments(
          participant,
          destination,
          batch.current,
          setProgress,
        );
        if (generation.current !== currentGeneration) return;
        onShared({
          id: batch.current.requestId,
          timestamp: Date.now(),
          message:
            batch.current.question ||
            "Please describe or summarize these attachments.",
          files: files.map(({ file, preview }) => ({
            name: file.name,
            preview,
          })),
        });
        // URLs now belong to the transcript; retain them until this workspace unmounts.
        setFiles([]);
        batch.current = null;
        setUncertain(false);
      } else {
        await onText(draft.trim());
        if (generation.current !== currentGeneration) return;
      }
      setDraft("");
      onSent?.();
    } catch (error) {
      if (generation.current !== currentGeneration) return;
      const pendingReceipt = !!batch.current?.committing;
      setUncertain(pendingReceipt);
      onError(
        pendingReceipt
          ? "The receipt was interrupted; your message may have arrived. Retry to check its receipt without sending another copy."
          : error instanceof Error
            ? error.message
            : "Your message could not be sent. Please try again.",
      );
    } finally {
      if (generation.current === currentGeneration) {
        setBusy(false);
        sending.current = false;
      }
    }
  }
  return (
    <div
      className={`sharing-composer ${dragging ? "drop-active" : ""}`}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) {
          event.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node))
          setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        add(Array.from(event.dataTransfer.files));
      }}
      onPaste={(event) => {
        const pasted = Array.from(event.clipboardData.files);
        if (pasted.length) {
          event.preventDefault();
          add(pasted);
        }
      }}
    >
      {files.length > 0 && (
        <div className="attachment-tray" aria-label="Attachments ready to send">
          {files.map(({ file, preview }, index) => (
            <div className="attachment-chip" key={`${file.name}-${index}`}>
              {preview ? (
                <img src={preview} alt={`Preview of ${file.name}`} />
              ) : (
                <FileText size={20} />
              )}
              <span>
                {file.name}
                <small>{Math.ceil(file.size / 1024)} KB</small>
              </span>
              <button
                type="button"
                aria-label={`Remove ${file.name}`}
                disabled={busy || uncertain}
                onClick={() => remove(index)}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {busy && files.length > 0 && (
        <div className="upload-status" role="status">
          {progress < 1
            ? `Sharing files · ${Math.round(progress * 100)}%`
            : "Waiting for Ariana’s receipt…"}
        </div>
      )}
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <input
          ref={picker}
          type="file"
          className="sr-only"
          multiple
          accept={ACCEPT_FILES}
          aria-label="Choose attachments"
          onChange={(event) => {
            add(Array.from(event.target.files || []));
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="attach-button"
          aria-label="Attach files or pictures"
          disabled={busy || uncertain || files.length >= MAX_FILES}
          onClick={() => picker.current?.click()}
        >
          <Paperclip size={18} />
        </button>
        <input
          ref={inputRef}
          value={draft}
          disabled={busy || uncertain}
          onChange={(event) => {
            setDraft(event.target.value);
            if (!batch.current?.committing) batch.current = null;
          }}
          placeholder={
            files.length
              ? "Ask about your attachments…"
              : ready
                ? "Or type a message…"
                : "Enter a message…"
          }
          aria-label="Message Ariana"
          maxLength={4000}
        />
        <button
          aria-label={uncertain ? "Retry attachment receipt" : "Send message"}
          disabled={!ready || (!draft.trim() && !files.length) || busy}
        >
          {busy ? (
            <LoaderCircle size={19} className="spin" />
          ) : (
            <ArrowUp size={20} />
          )}
        </button>
      </form>
      <div className="composer-hint">
        {uncertain
          ? "Retry checks the original send · end the session to reset"
          : "Paste or drop pictures & files · up to 3 files, 10 MB each"}
      </div>
    </div>
  );
}
