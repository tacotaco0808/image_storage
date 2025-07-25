from uuid import UUID
from fastapi import WebSocket
from starlette.websockets import WebSocketState


class ConnectionManager():
    def __init__(self) -> None:
        self.websockets:dict[str, WebSocket] = {}

    async def addWebSocket(self, websocket: WebSocket, user_id: str):
        if user_id in self.websockets:
            existing_ws = self.websockets[user_id]
            if existing_ws.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=4001, reason="User already connected")
                return False
            else:
                # 既存WebSocketが切断済みならリストから除去して新規接続を許可
                self.websockets.pop(user_id)
        if websocket not in self.websockets:
            await websocket.accept()
            self.websockets[user_id] = websocket
            return True
        return False

    async def sendMessage (self,websocket:WebSocket,string:str):
        await websocket.send_text(f"From Server : {string}")

    async def broadCastMessage(self,string:str):
        for ws in self.websockets.values():
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(f"{string}")
        
    async def broadCastJson(self,json_data,user_id:str):
        for ws in self.websockets.values():
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_json(json_data)
            else:
               await self.deleteWebSocket(ws,user_id)

        
    async def deleteWebSocket(self, websocket: WebSocket,user_id:str):
        try:
            if user_id in self.websockets:
                await websocket.close()
                self.websockets.pop(user_id)
        except ValueError as e:
            print(f"WebSocket already removed: {e}")
        except Exception as e:
            print(f"Error removing websocket: {e}")


    