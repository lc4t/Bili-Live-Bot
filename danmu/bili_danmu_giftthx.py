
import asyncio
import traceback
import json
import copy
import datetime
import random
import time
import re
import queue
from printer import info as print
from danmu.bili_abc import bili_danmu
from reqs.utils import UtilsReq
from reqs.custom import BanUserReq
from .bili_danmu import WsDanmuClient


DELAY = 0


class DanmuGiftThx(WsDanmuClient):

    # GIFT_MSG = '谢谢可爱的{username}投喂{giftname}x{num} (╭￣3￣)╭♡'
    # DELAY_SECOND = 3

    async def set_user(self, user):
        self.user = user
        self.GIFT_QUEUE = queue.Queue()
        self.pk_end_time = -1
        self.end = True
        self.pk_me_votes = 0
        self.pk_op_votes = 0
        self.pk_now_use = 0
        print(f'已关联用户{self.user.alias} -> {self._room_id}')
        await self._is_alive()

    async def _is_alive(self):
        json_rsp = await self.user.req_s(UtilsReq.init_room, self.user, self._room_id)
        status = json_rsp.get('data', {}).get('live_status')
        self.is_live = status == 1
        return self.is_live

    async def run_alter(self):
        if len(self.user.alerts) == 0:
            print('感谢🐔公告循环内容为空')
            return
        now = 0

        while(1):
            if self.is_live:
                text = self.user.alerts[now % len(self.user.alerts)]
                await self.send_danmu(text)
                now += 1
            else:
                print(f'{self._room_id}未开播, {datetime.datetime.now()}')
            await asyncio.sleep(self.user.alert_second)

    async def run_medal_update(self):
        json_rsp = await self.user.req_s(UtilsReq.get_room_info, self.user, self._room_id)
        uid = json_rsp.get('data', {}).get('uid', 0)

        if uid == 0:
            print('获取uid失败，重启或检查房间号')
            return

        if not self.user.medal_update_format:
            print('medal_update_format未定义，勋章升级提醒关闭')
            return

        async def get_medals():
            medal_data = {}
            json_rsp = await self.user.req_s(UtilsReq.get_room_medal, self.user, self._room_id, uid, 1)
            total_page = json_rsp.get('data', {}).get('total_page', 1)
            medal_data.update({x.get('uid'): {'level': x.get('level'), 'uname': x.get('uname')}
                               for x in json_rsp.get('data', {}).get('list', [])})
            if total_page > 1:
                for p in range(2, total_page+1):
                    json_rsp = await self.user.req_s(UtilsReq.get_room_medal, self.user, self._room_id, uid, p)
                    medal_data.update({x.get('uid'): {'level': x.get('level'), 'uname': x.get(
                        'uname')} for x in json_rsp.get('data', {}).get('list', [])})
            return medal_data

        medal_rank_already = await get_medals()

        while(1):
            try:
                medal_rank = copy.deepcopy(await get_medals())
                # print(f'already={medal_rank_already}')
                # print(f'new={medal_rank}')
                for mid, info in medal_rank.items():
                    if mid not in medal_rank_already:
                        # 牌子新获取
                        uname = medal_rank[mid].get('uname')
                        new_level = medal_rank[mid].get('level')
                        old_level = 0
                        await self.send_danmu(self.user.medal_update_format.format(username=uname, uid=mid, new_level=new_level, old_level=old_level))
                    elif mid in medal_rank_already and info.get('level', 0) > medal_rank_already[mid].get('level', 0):
                        # 牌子升级
                        uname = medal_rank[mid].get('uname')
                        new_level = medal_rank[mid].get('level')
                        old_level = medal_rank_already[mid].get('level', 0)

                        await self.send_danmu(self.user.medal_update_format.format(username=uname, uid=mid, new_level=new_level, old_level=old_level))
                    else:
                        pass
                medal_rank_already = copy.deepcopy(medal_rank)

            except:
                traceback.print_exc()
            await asyncio.sleep(self.user.medal_update_check_delay)

    async def run_fans(self):
        # 获取uid
        json_rsp = await self.user.req_s(UtilsReq.get_room_info, self.user, self._room_id)
        uid = json_rsp.get('data', {}).get('uid', 0)

        if uid == 0:
            print('获取uid失败，重启或检查房间号')
            return
        fans_already = set()
        now = int(time.time())
        while(1):
            try:
                json_rsp = await self.user.req_s(UtilsReq.get_user_follower, self.user, uid)
                # print(json_rsp)
                fans = json_rsp.get('data', {}).get('list', [])
                for u in fans:
                    mid = u.get('mid', 0)
                    mtime = u.get('mtime', 0)
                    uname = u.get('uname', '')
                    if uname and mid and mtime:
                        if mtime < now:
                            continue
                        if mid in fans_already:
                            continue
                        await self.send_danmu(self.user.focus_thx_format.format(username=uname,
                                                                                random1=random.choice(
                                                                                    self.user.random_list_1),
                                                                                random2=random.choice(
                                                                                    self.user.random_list_2),
                                                                                random3=random.choice(self.user.random_list_3)))
                        fans_already.add(mid)
            except:
                traceback.print_exc()
            await asyncio.sleep(self.user.fans_check_delay)

    async def run_sender(self):
        roomid = self._room_id
        wait_to_send_danmu = {}     # 礼物列表合并后的输出
        sem = asyncio.Semaphore(1)
        while(1):
            # 取出所有结果，添加到等待队列
            # 如果某个room-user-gift保持了5s不动，则推出
            async with sem:
                qlength = self.GIFT_QUEUE.qsize()
                cache_gift = []
                for i in range(qlength):
                    cache_gift.append(self.GIFT_QUEUE.get())
            # print(cache_gift)
            # cache_gift是所有没处理的送礼物的信息
            # 现在将他们合并为一个list
            for gift_info in cache_gift:
                if gift_info.get('room') != roomid:
                    print('error room id')
                    exit(0)
                # 拿到单条礼物信息
                username, gift_name, gift_num, t, coin_type, total_coin = gift_info.get('username'), gift_info.get(
                    'gift_name'), gift_info.get('gift_num'), gift_info.get('t'),  gift_info.get('coin_type'), gift_info.get('total_coin')
                # 以用户名为主键
                if username not in wait_to_send_danmu:
                    wait_to_send_danmu[username] = {}    # 新建username
                # 礼物名为主键
                if f'{gift_name}_{coin_type}' not in wait_to_send_danmu.get(username):
                    wait_to_send_danmu[username].update(
                        {f'{gift_name}_{coin_type}': {
                            'gift_num': gift_num,
                            'coin_type': coin_type,
                            'total_coin': total_coin,
                            't': t,
                        }})   # username->gift_name
                else:
                    # 查找已经送了的有多少
                    already_num = wait_to_send_danmu[username].get(
                        f'{gift_name}_{coin_type}', {}).get('gift_num', 0)  # 已经送了的
                    already_total_coin = wait_to_send_danmu[username].get(
                        f'{gift_name}_{coin_type}', {}).get('total_coin', 0)  # 已经送了的总价值

                    wait_to_send_danmu[username][f'{gift_name}_{coin_type}'].update(
                        {
                            'gift_num': gift_num + already_num,
                            't': t,
                            'total_coin': total_coin+already_total_coin
                        })  # 更新数量

            # print(wait_to_send_danmu)

            # 检查时间是否达到推出标准
            # 这里可以重写感谢弹幕

            for username, gifts in wait_to_send_danmu.items():
                for gift_name, info in gifts.items():
                    gift_num = info.get('gift_num')
                    coin_type = info.get('coin_type')
                    total_coin = info.get('total_coin', 0)
                    gift_name_true = gift_name.strip(f'_{coin_type}')
                    fstr = ''
                    if coin_type == 'silver':
                        fstr = self.user.silver_gift_thx_format
                    else:
                        fstr = self.user.gold_gift_thx_format
                    if gift_num == 0:
                        continue
                    if time.time() - info.get('t') > self.user.gift_comb_delay:
                        if self.is_live or (not self.user.only_live_thx):

                            # self.user.gift_thx_silver_format
                            await self.send_danmu(fstr.format(username=username,
                                                              num=gift_num,
                                                              total_coin=total_coin,
                                                              giftname=gift_name_true,
                                                              random1=random.choice(
                                                                  self.user.random_list_1),
                                                              random2=random.choice(
                                                                  self.user.random_list_2),
                                                              random3=random.choice(self.user.random_list_3)))
                            await self.game_log(coin_type, total_coin)
                        wait_to_send_danmu[username][gift_name].update(
                            {'gift_num': 0, 'total_coin': 0})

            await asyncio.sleep(1)

    async def send_danmu(self, text, default_length=30):
        return
        # print('try:', text, len(text))
        default_length = self.user.danmu_length
        msg = text[0:default_length]
        json_rsp = await self.user.req_s(UtilsReq.send_danmu, self.user, msg, self._room_id)
        # print(json_rsp)
        if json_rsp.get('msg', '') == 'msg in 1s':
            await asyncio.sleep(0.5)
            return await self.send_danmu(text, default_length, retry)
        elif json_rsp.get('msg', '') == '':
            pass
        elif json_rsp.get('msg', '') == '内容非法':
            print(f'{text} --> {retry}')
            print(json_rsp)
            text = self.replace_num(text)
            return await self.send_danmu(text, default_length, retry-1)
        elif json_rsp.get('msg', '') == 'msg repeat':
            await asyncio.sleep(0.5)
            return await self.send_danmu(text, default_length, retry-3)
        elif json_rsp.get('msg', '') == '超出限制长度':
            print(text)
            print(json_rsp)
            return await self.send_danmu(text, default_length-10, retry)

        if len(text) > default_length:
            await asyncio.sleep(1)
            await self.send_danmu(text[default_length:], default_length, retry)

    async def game_log(self, coin_type, total_coin):
        if coin_type == 'silver':
            self.user.height += total_coin
        elif coin_type == 'gold':
            self.user.weight += total_coin
        else:
            print(f'unknow {coin_type} {total_coin}')
        self.user.update_log()

    async def get_gamestr(self):
        weight, height = '', ''
        if int(self.user.weight) < 10**3:
            weight = '%dmg' % (self.user.weight)
        elif 10**3 <= int(self.user.weight) < 10**6:
            weight = '%.3fg' % (self.user.weight/(10**3))
        elif 10**6 <= int(self.user.weight) < 10**9:
            weight = '%.4fkg' % (self.user.weight/(10**6))
        else:
            # elif 10**9 <= self.user.weight:
            weight = '%.5ft' % (self.user.weight/(10**9))

        # 1au = 149 597 871km
        # 1光秒 299792.458 km
        if int(self.user.height) < 10**3:
            height = '%dmm' % (self.user.height)
        elif 10**3 <= int(self.user.height) < 10**6:  # 1m - 1km
            height = '%.3fm' % (self.user.height/(10**3))
        elif 10**6 <= int(self.user.height) < 10**9:  # < 1km - 1kkm
            height = '%.4fkm' % (self.user.height/(10**6))
        elif 10**9 <= self.user.height < 86400 * 299792458000:  # 光天
            height = '%.4f光秒' % (self.user.height/(299792458000))
        else:
            height = '%.5f光年' % (self.user.height/(10**6)/149597870.7)
        return weight, height
        # elif 10**9 <= self.user.height:
        #     height = '%.5ft' % self.user.height/(10**9)

    async def auto_reply(self, username: str, uid: int, danmu: str):
        # [{'key': '^.*(好听).*$', 'percent': 1, 'reply': '好听赶紧关注啊！'}]
        weight, height = await self.get_gamestr()
        for r in self.user.reply:
            key = r.get('key')
            percent = float(r.get('percent', 1))
            reply = r.get('reply')

            check = re.findall(key, danmu)
            if len(check) > 0 and len(check[0])/len(danmu) >= percent:
                await self.send_danmu(reply.format(weight=weight, height=height))
                return

    async def auto_ban(self, username: str, uid: int, danmu: str):
        for r in self.user.ban:
            key = r.get('key')
            percent = float(r.get('percent', 1))
            hour = int(r.get('hour', 720))

            check = re.findall(key, danmu)
            if len(check) > 0 and len(check[0])/len(danmu) >= percent:
                json_rsp = await self.user.req_s(BanUserReq.ban_user, self.user, self._room_id, uid, int(hour))
                print(json_rsp)
                return

    async def pk_bd(self):
        # PK偷塔
        json_rsp = await self.user.req_s(UtilsReq.get_room_info, self.user, self._room_id)
        ruid = json_rsp.get('data', {}).get('uid', 0)

        if ruid == 0:
            print('获取uid失败，重启或检查房间号')
            return
        # 笔芯 20014
        # await asyncio.sleep(3)

        while(1):
            try:
                if self.pk_end_time > time.time() or not self.end:
                    # print(
                    #     f'PK还有{self.pk_end_time - time.time()}s结束, 分差{self.pk_op_votes-self.pk_me_votes}')
                    if self.pk_end_time - time.time() < 1 and self.pk_op_votes - self.pk_me_votes >= 0 and self.pk_end_time - time.time() > -5:
                        # print(f'开启偷塔, 时限{self.pk_end_time - time.time()}')
                        # print(f'当前分差{self.pk_op_votes-self.pk_me_votes}')
                        if self.pk_op_votes - self.pk_me_votes > self.user.pk_max_votes or self.pk_now_use > self.user.pk_max_votes:
                            # print('超额了', self.pk_op_votes - self.pk_me_votes,
                            #       self.user.pk_max_votes, self.pk_now_use, self.user.pk_max_votes)
                            continue
                        need = ((self.pk_op_votes-self.pk_me_votes)/self.user.pk_gift_rank)+3
                        gift_id = self.user.pk_gift_id  # 这个礼物是52分 20014
                        gift_num = need
                        print(f'赠送{need}个{self.user.pk_gift_id}')
                        # print(UtilsReq.send_gold, self.user, gift_id, gift_num, self._room_id, ruid)
                        self.pk_now_use += self.user.pk_gift_rank*need
                        json_rsp = await self.user.req_s(UtilsReq.send_gold, self.user, gift_id, gift_num, self._room_id, ruid)
                        # status = json_rsp.get('data', {}).get('live_status')
                        # print(json_rsp)

                        # continue
                        # await asyncio.sleep(0.1)
            except:
                traceback.print_exc()

            await asyncio.sleep(0.1)

    async def handle_danmu(self, data: dict):
        cmd = data['cmd']

        # print(data)
        try:
            # self.user.height += 1
            # self.user.update_log()
            if cmd == 'DANMU_MSG':
                flag = data['info'][0][9]
                # if flag == 0:
                #     print(
                #         f"{data['info'][2][1]}({data['info'][2][0]})在{self._room_id}: {data['info'][1]}")
            elif cmd == 'SEND_GIFT':
                room_id = self._room_id
                user_id = data['data']['uid']
                username = data['data']['uname']

                gift_name = data['data']['giftName']
                gift_num = data['data']['num']
                coin_type = data['data']['coin_type']
                total_coin = data['data']['total_coin']
                self.GIFT_QUEUE.put({
                    'room': room_id,
                    'username': username,
                    'uid': user_id,
                    'gift_name': gift_name,
                    'gift_num': int(gift_num),
                    't': time.time(),
                    'coin_type': coin_type,
                    'total_coin': total_coin,

                })

            elif cmd == 'GUARD_BUY':
                # user_id=data['data']['uid'],
                username = data['data']['username']
                gift_name = data['data']['gift_name']
                gift_num = data['data']['num']
                if self.is_live or (not self.user.only_live_thx):
                    await self.send_danmu(self.user.guard_thx_format.format(username=username, num=gift_num, giftname=gift_name))

            elif cmd == 'PK_BATTLE_START':
                print(data)
                self.end = False
                self.pk_now_use = 0
                self.pk_me_votes = 0
                self.pk_op_votes = 0

                pk_id = data.get('pk_id')
                t = data.get('timestamp')
                self.pk_end_time = data.get('data').get('pk_end_time') - 10 + DELAY

            elif cmd == 'PK_BATTLE_PROCESS':
                print(data)
                self.end = False
                pk_id = data.get('pk_id')
                t = data.get('timestamp')
                # data = data.get('data')

                init_info = data.get('data').get('init_info')
                match_info = data.get('data').get('match_info')

                if init_info.get('room_id') != self._room_id:
                    # 交换
                    init_info, match_info = match_info, init_info

                if init_info.get('room_id') == self._room_id:
                    me_roomid, self.pk_me_votes, me_best = init_info.get(
                        'room_id'), init_info.get('votes'), init_info.get('best_uname')
                    op_roomid, self.pk_op_votes, op_best = match_info.get(
                        'room_id'), match_info.get('votes'), match_info.get('best_uname')
                    print(
                        f'和对方差距{self.pk_op_votes-self.pk_me_votes}分, {self.pk_end_time-time.time()}s后结束')
                else:
                    print('error获取pk信息:')
                    print(data)

            elif cmd == 'PK_BATTLE_END':
                print(data)
                self.pk_now_use = 0
                self.end = True

                pk_id = data.get('pk_id')
                t = data.get('timestamp')

                init_info = data.get('data').get('init_info')
                match_info = data.get('data').get('match_info')

                if init_info.get('room_id') != self._room_id:
                    # 交换
                    init_info, match_info = match_info, init_info

                if init_info.get('room_id') == self._room_id:
                    me_roomid, self.pk_me_votes, me_best, me_win = init_info.get(
                        'room_id'), init_info.get('votes'), init_info.get('best_uname'), init_info.get('winner_type')
                    op_roomid, self.pk_op_votes, op_best, op_win = match_info.get('room_id'), match_info.get(
                        'votes'), match_info.get('best_uname'), match_info.get('winner_type')
                    print(f'结束了，与对方分差{self.pk_op_votes-self.pk_me_votes}分，最佳应援{me_best}')
                    self.pk_end_time = -1
                else:
                    print('error获取pk信息:')
                    print(data)
            elif cmd in ['PK_BATTLE_SETTLE_USER', 'PK_BATTLE_SETTLE']:
                self.end = True
                print(data)
            elif cmd == 'PK_BATTLE_PRO_TYPE':
                print(data)
                print('绝杀')
                t = data.get('timestamp')
                delay = data.get('data').get('timer')
                self.pk_end_time = t + delay + DELAY
            elif cmd.startswith('ANCHOR'):
                print(data)
            # elif cmd in ['WELCOME_GUARD', 'WELCOME', 'NOTICE_MSG', 'SYS_GIFT', 'ACTIVITY_BANNER_UPDATE_BLS', 'ENTRY_EFFECT', 'ROOM_RANK', 'ACTIVITY_BANNER_UPDATE_V2', 'COMBO_END', 'ROOM_REAL_TIME_MESSAGE_UPDATE', 'ROOM_BLOCK_MSG', 'WISH_BOTTLE', 'WEEK_STAR_CLOCK', 'ROOM_BOX_MASTER', 'HOUR_RANK_AWARDS', 'ROOM_SKIN_MSG', 'RAFFLE_START', 'RAFFLE_END', 'GUARD_LOTTERY_START', 'GUARD_LOTTERY_END', 'GUARD_MSG', 'USER_TOAST_MSG', 'SYS_MSG', 'COMBO_SEND', 'ROOM_BOX_USER', 'TV_START', 'TV_END', 'ANCHOR_LOT_END', 'ANCHOR_LOT_AWARD', 'ANCHOR_LOT_CHECKSTATUS', 'ANCHOR_LOT_STAR', 'ROOM_CHANGE', 'LIVE', 'new_anchor_reward', 'room_admin_entrance', 'ROOM_ADMINS', 'PREPARING']:
            #     pass
            else:
                print(data)
        except:
            traceback.print_exc()
            print(data)
        return True


# {"code":0,"msg":"","message":"","data":{"id":4099580,"uname":"bishi","block_end_time":"2020-01-03 17:36:18"}}
# {'code': -400, 'msg': '此用户已经被禁言了', 'message': '此用户已经被禁言了', 'data': []}
