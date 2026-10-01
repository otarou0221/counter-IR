"""内部HTTPサービスとの共用接続。"""

from __future__ import annotations

from fastapi import HTTPException
import httpx


class ServiceClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(self, url: str) -> dict[str, object]:
        await self.start()
        try:
            response = await self._require_client().get(url)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"内部サービスへ接続できません: {exc}") from exc
        return response_json(response)

    async def post_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        await self.start()
        try:
            response = await self._require_client().post(url, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"内部サービスへ接続できません: {exc}") from exc
        return response_json(response)

    async def put_json(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        await self.start()
        try:
            response = await self._require_client().put(url, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"内部サービスへ接続できません: {exc}") from exc
        return response_json(response)

    async def delete_json(self, url: str) -> dict[str, object]:
        await self.start()
        try:
            response = await self._require_client().delete(url)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"内部サービスへ接続できません: {exc}") from exc
        return response_json(response)

    async def open_stream(self, url: str) -> httpx.Response:
        """内部サービスのストリームを開き、呼出側へ所有権を渡す。"""
        await self.start()
        client = self._require_client()
        try:
            response = await client.send(client.build_request("GET", url), stream=True)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"内部サービスへ接続できません: {exc}",
            ) from exc
        if response.is_error:
            await response.aread()
            try:
                response_json(response)
            finally:
                await response.aclose()
        return response

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HTTPクライアントが起動していません")
        return self._client


def response_json(response: httpx.Response) -> dict[str, object]:
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    value = response.json()
    if not isinstance(value, dict):
        raise HTTPException(status_code=502, detail="内部サービスの応答形式が不正です")
    return value
