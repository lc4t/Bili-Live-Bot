import re

from bili_global import API_LIVE
from json_rsp_ctrl import ZERO_ONLY_CTRL


class PkRaffleHandlerReq:
    @staticmethod
    async def check(user, real_roomid):
        url = f'{API_LIVE}/xlive/lottery-interface/v1/lottery/Check?roomid={real_roomid}'
        json_rsp = await user.bililive_session.request_json('GET', url, ctrl=ZERO_ONLY_CTRL)
        # data.pk[0].id
        ##
        return json_rsp

    @staticmethod
    async def join(user, real_roomid, pk_id):
        url = f"{API_LIVE}/xlive/lottery-interface/v2/pk/join"

        data = {
            'roomid': real_roomid,
            'id': pk_id,
            'type': 'pk',
            'csrf_token': user.dict_user['csrf'],
            'csrf': user.dict_user['csrf'],
        }
        response = await user.bililive_session.request_json('POST', url, data=data,
                                                            headers=user.pc.headers)
        return response

    @staticmethod
    async def info(user, pk_id, room_id):
        url = f'{API_LIVE}/av/v1/Battle/getInfoById?pk_id={pk_id}&roomid={room_id}&pk_version=2'
        json_rsp = await user.bililive_session.request_json('GET', url, ctrl=ZERO_ONLY_CTRL)
        return json_rsp

    @staticmethod
    async def init(user, room_id):
        url = f'https://live.bilibili.com/{room_id}'
        rsp = await user.bililive_session.request_text('GET', url)
        # print(rsp)
        check = re.findall(r'\{\"pk_id\"\:([0-9]+)\}', rsp)
        # print(check)
        if check:
            return check[0]
        else:
            return 0
