import json
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from auth import get_current_user_ws
from websocket import ConnectionManager
from eventHandler import EventHandler

# WebSocket関連のグローバル変数
wsmanager = ConnectionManager()
event_handler = EventHandler(wsmanager)

async def websocket_endpoint(websocket: WebSocket, ws_id: str):# ws_idは接続してきたクライアントのID
    # ユーザ認証
    current_user = await get_current_user_ws(websocket, websocket.app)
    if not current_user:
        await websocket.close(code=4003, reason="Unauthorized")
        print(f"WebSocket認証失敗: {ws_id}")
        return 
    
    # 接続リストへ追加
    await wsmanager.addWebSocket(websocket, ws_id)

    # すでにサーバに接続されているクライアントを画面に反映する
    for user_id, ws in wsmanager.websockets.items():
        if not ws_id == user_id and not ws.client_state == WebSocketState.DISCONNECTED:
            await wsmanager.sendJson({"event": "login", "player_id": user_id}, ws_id, websocket)
            
    # 既存参加中のユーザに向けて自分のログインを通知
    await wsmanager.broadCastJson({"event": "login", "player_id": ws_id}, ws_id)
    
    try:
        while(True):
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                print(f"From Client:{event}", flush=True)
                await event_handler.handle(event=event, websocket=websocket, user_id=ws_id)

            except Exception as e:
                print(f"Event handling error: {e}")
    except WebSocketDisconnect:
        print(f"WebSocket正常切断: {ws_id}")
        await _handle_disconnect(ws_id, "logout")
    except RuntimeError as e:
        print(f"WebSocketランタイムエラー: {ws_id}, {e}")
        await _handle_disconnect(ws_id, "logout!")
    except Exception as e:
        print(f"WebSocket予期しないエラー: {ws_id}, {e}")
        await _handle_disconnect(ws_id, "logout!!")

async def _handle_disconnect(ws_id: str, event_type: str):
    """切断時の共通処理"""
    try:
        await wsmanager.broadCastJson({"event": event_type, "player_id": ws_id}, ws_id)
        # websocketオブジェクトはwsmanager内で管理されているため、ws_idで削除
        if ws_id in wsmanager.websockets:
            websocket = wsmanager.websockets[ws_id]
            await wsmanager.deleteWebSocket(websocket, ws_id)
    except Exception as e:
        print(f"切断処理エラー: {ws_id}, {e}")
        
