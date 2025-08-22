from uuid import UUID
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

class ConnectionManager():
    def __init__(self) -> None:
        self.websockets:dict[str, WebSocket] = {}

    async def addWebSocket(self, websocket: WebSocket, user_id: str):
        print(f"✅✅")
        print(f"websockets: {self.websockets}")
        for key,ws in self.websockets.items():
            print(f"✅✅✅")
            print(f"key:{key}|ws:{ws}|status:{ws.client_state}")

        if user_id in self.websockets:
            print(f"リストにダブりがある--→")
            if self.websockets[user_id].client_state == WebSocketState.DISCONNECTED:
                self.websockets.pop(user_id)
                await websocket.accept()
                self.websockets[user_id] = websocket
                print(f"✅✅✅✅正常に追加されたよ")
                print(f"------------------->{user_id}")
                print(f"------------------->{websocket}")
            else:
                print(f"✖リストにダブりがある")
        else:
            await websocket.accept()
            self.websockets[user_id] = websocket
            print(f"✅正常に追加されたよ")
            print(f"------------------->{user_id}")
            print(f"------------------->{websocket}")

        

        # if user_id in self.websockets:
        #     existing_ws = self.websockets[user_id]
        #     if existing_ws.client_state == WebSocketState.CONNECTED:
        #         await websocket.close(code=4001, reason="User already connected")
        #         return False
        #     else:
        #         # 既存WebSocketが切断済みならリストから除去して新規接続を許可
        #         self.websockets.pop(user_id)
        # if websocket not in self.websockets:
        #     await websocket.accept()
        #     self.websockets[user_id] = websocket
        #     return True
        # return False

    # async def sendMessage (self,websocket:WebSocket,string:str):
    #     await websocket.send_text(f"From Server : {string}")

    async def sendJson(self, json_data,user_id,websocket: WebSocket):
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(json_data)
        else:
            await self.deleteWebSocket(websocket,user_id)


    async def broadCastMessage(self,string:str):
        for ws in self.websockets.values():
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_text(f"{string}")
        
    async def broadCastJson(self, json_data, user_id: str):
        # user_idは送信したくないクライアントのID
        for key_id, ws in self.websockets.items():
            if key_id == user_id:
                continue  # 自分自身には送信しない
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(json_data)
                else:
                    await self.deleteWebSocket(ws, key_id)
            except WebSocketDisconnect:
                await self.deleteWebSocket(ws, key_id)

        
    async def deleteWebSocket(self, websocket: WebSocket,user_id:str):
        try:
            if user_id in self.websockets and websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
                self.websockets.pop(user_id)
                print(f"✅正常に削除されたよ")
                print(f"------------------->{user_id}")
                print(f"------------------->{websocket}")
        except ValueError as e:
            print(f"WebSocket already removed: {e}")
        except Exception as e:
            print(f"Error removing websocket: {e}")


    