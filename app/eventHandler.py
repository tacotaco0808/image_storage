from websocket import ConnectionManager


class EventHandler:
    def __init__(self,wsmanager) -> None:
        self.wsmanager:ConnectionManager = wsmanager

    async def handle(self,event,websocket,user_id):
        # websocket,user_idは接続してきたクライアントのもの
        event_type = event["event"]
        handler = getattr(self,f"on_{event_type}",self.on_unknown)
        await handler(event,websocket) # 受信したイベントタイプの関数を実行,デフォはon_unlnown
        await self.wsmanager.broadCastJson(event,user_id)
    async def on_position(self,event,websocket):
        print("positionイベント",event)
    
    async def on_unknown(self,event,websocket):
        print("デフォルトイベント",event)