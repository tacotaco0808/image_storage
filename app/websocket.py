from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

class ConnectionManager():
    def __init__(self) -> None:
        self.websockets: dict[str, WebSocket] = {}

    async def addWebSocket(self, websocket: WebSocket, user_id: str) -> None:        
        # 重複接続の処理
        if user_id in self.websockets:
            await self._replace_existing_connection(user_id)
        
        # 新規接続を受け入れ
        await websocket.accept()
        self.websockets[user_id] = websocket
        self._log_connection(user_id, websocket, "追加")
        

    async def sendJson(self, json_data, user_id: str, websocket: WebSocket)->None:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(json_data)
        else:
            await self.deleteWebSocket(websocket, user_id)

    async def broadCastJson(self, json_data, exclude_user_id: str)->None:
        disconnected = []
        for user_id, ws in self.websockets.items():
            if user_id == exclude_user_id:
                continue
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(json_data)
                else:
                    disconnected.append(user_id)
            except WebSocketDisconnect:
                disconnected.append(user_id)
        
        # 切断されたWebSocketを一括削除
        for user_id in disconnected:
            self.websockets.pop(user_id, None)

    async def deleteWebSocket(self, websocket: WebSocket, user_id: str)->None:
        try:
            if user_id in self.websockets:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close()
                self.websockets.pop(user_id)
                self._log_connection(user_id, websocket, "削除")
        except Exception as e:
            print(f"Error removing websocket for {user_id}: {e}")

    async def _replace_existing_connection(self, user_id: str) -> None:
        """既存接続を置き換える"""
        existing_ws = self.websockets[user_id]
        
        if existing_ws.client_state == WebSocketState.CONNECTED:
            # 既存接続に警告メッセージを送信
            try:
                await existing_ws.send_json({
                    "event": "connection_replaced",
                    "message": "別のデバイスから新しい接続が確立されたため、この接続を切断します",
                    "reason": "New connection from same user"
                })
            except Exception as e:
                print(f"Warning message send failed for {user_id}: {e}")
                
            # 既存接続を切断
            try:
                await existing_ws.close(code=4002, reason="New connection from same user")
            except Exception as e:
                print(f"既存接続のクローズ中にエラー: {user_id}, {e}")
        
        # 接続状態に関わらず削除
        self.websockets.pop(user_id)

    def _log_connection(self, user_id: str, websocket: WebSocket, action: str):
        """接続ログの共通処理"""
        print(f"✅WebSocket{action}されたよ")
        print(f"User ID: {user_id}")
        print(f"WebSocket: {websocket}")
        print(f"現在の接続数: {len(self.websockets)}")


