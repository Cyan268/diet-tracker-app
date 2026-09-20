import * as Crypto from "expo-crypto";
import type { UploadPresignResponse, UploadResponse } from "@/api/types";
import { requestJson } from "@/api/http";
import type { AuthRequestScope } from "@/features/auth/authSession";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

function bytesToHex(value: ArrayBuffer): string {
  return Array.from(new Uint8Array(value), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function jpegBase64ToBytes(base64: string): Promise<Uint8Array> {
  const response = await fetch(`data:image/jpeg;base64,${base64}`);
  return new Uint8Array(await response.arrayBuffer());
}

export async function uploadAnalysisImage(
  scope: AuthRequestScope,
  jpegBytes: Uint8Array
): Promise<UploadResponse> {
  if (jpegBytes.byteLength === 0 || jpegBytes.byteLength > MAX_IMAGE_BYTES) {
    throw new Error("图片必须小于 10 MB");
  }
  scope.assertCurrent();
  const body = jpegBytes.buffer.slice(
    jpegBytes.byteOffset,
    jpegBytes.byteOffset + jpegBytes.byteLength
  ) as ArrayBuffer;
  const digest = bytesToHex(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, body));
  scope.assertCurrent();
  const contract = await scope.request<UploadPresignResponse>("/api/v1/uploads/presign", {
    method: "POST",
    body: JSON.stringify({
      content_type: "image/jpeg",
      size: jpegBytes.byteLength,
      sha256: digest,
    }),
  });
  try {
    await requestJson<void>(fetch, contract.upload_url, {
      method: "PUT",
      headers: { "Content-Type": contract.required_content_type },
      body,
    });
    scope.assertCurrent();
    return await scope.request<UploadResponse>(`/api/v1/uploads/${contract.upload_id}/complete`, {
      method: "POST",
    });
  } catch (error) {
    await scope
      .request<void>(`/api/v1/uploads/${contract.upload_id}`, { method: "DELETE" })
      .catch(() => undefined);
    throw error;
  }
}
