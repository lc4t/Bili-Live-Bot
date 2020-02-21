from .bili_danmu import WsDanmuClient
import asyncio
import traceback
import json
import datetime
import random
import time
import queue
from printer import info as print
from reqs.utils import UtilsReq


DELAY = 0


class DanmuGiftThx(WsDanmuClient):

    # GIFT_MSG = '谢谢可爱的{username}投喂{giftname}x{num} (╭￣3￣)╭♡'
    # DELAY_SECOND = 3

    def set_user(self, user):
        self.user = user
        self.GIFT_QUEUE = queue.Queue()
        self.pk_end_time = -1
        self.end = True
        self.pk_me_votes = 0
        self.pk_op_votes = 0
        self.pk_now_use = 0
        print(f'已关联用户{self.user.alias} -> {self._room_id}')

    async def run_alter(self):
        if len(self.user.alerts) == 0:
            print('感谢🐔公告循环内容为空')
            return
        now = 0

        while(1):
            json_rsp = await self.user.req_s(UtilsReq.init_room, self.user, self._room_id)
            status = json_rsp.get('data', {}).get('live_status')
            if status == 1:
                text = self.user.alerts[now % len(self.user.alerts)]
                await self.send_danmu(text)
                now += 1
            else:
                print(f'{self._room_id}未开播, {datetime.datetime.now()}')
            await asyncio.sleep(self.user.alert_second)

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
            await asyncio.sleep(3)

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
                username, gift_name, gift_num, t = gift_info.get('username'), gift_info.get(
                    'gift_name'), gift_info.get('gift_num'), gift_info.get('t')
                if username not in wait_to_send_danmu:
                    wait_to_send_danmu[username] = {}    # 新建username
                if gift_name not in wait_to_send_danmu.get(username):
                    wait_to_send_danmu[username].update(
                        {gift_name: {'gift_num': gift_num, 't': t}})   # username->gift_name
                else:
                    # 查找已经送了的有多少
                    already_num = wait_to_send_danmu[username].get(
                        gift_name, {}).get('gift_num', 0)  # 已经送了的
                    wait_to_send_danmu[username][gift_name].update(
                        {'gift_num': gift_num + already_num, 't': t})  # 更新数量

            # print(wait_to_send_danmu)

            # 检查时间是否达到推出标准
            # 这里可以重写感谢弹幕
            for username, gifts in wait_to_send_danmu.items():
                for gift_name, info in gifts.items():
                    gift_num = info.get('gift_num')
                    if gift_num == 0:
                        continue
                    if time.time() - info.get('t') > self.user.gift_comb_delay:
                        await self.send_danmu(self.user.gift_thx_format.format(username=username,
                                                                               num=gift_num,
                                                                               giftname=gift_name,
                                                                               random1=random.choice(
                                                                                   self.user.random_list_1),
                                                                               random2=random.choice(
                                                                                   self.user.random_list_2),
                                                                               random3=random.choice(self.user.random_list_3)))
                        wait_to_send_danmu[username][gift_name].update({'gift_num': 0})
            await asyncio.sleep(1)

    async def send_danmu(self, text, default_length=30):
        return
        # print('try:', text, len(text))
        default_length = self.user.danmu_length
        msg = text[0:default_length]
        json_rsp = await self.user.req_s(UtilsReq.send_danmu, self.user, msg, self._room_id)
        print(json_rsp)
        if json_rsp.get('msg', '') == 'msg in 1s':  # msg repeat 不处理了
            await asyncio.sleep(0.5)
            return await self.send_danmu(text, default_length)
        if len(text) > default_length:
            await asyncio.sleep(1)
            await self.send_danmu(text[default_length:], default_length)

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
                    if self.pk_end_time - time.time() < 1 and self.pk_op_votes - self.pk_me_votes >= 0:
                        # print(f'开启偷塔, 时限{self.pk_end_time - time.time()}')
                        # print(f'当前分差{self.pk_op_votes-self.pk_me_votes}')
                        if self.pk_op_votes - self.pk_me_votes > self.user.pk_max_votes or self.pk_now_use > self.user.pk_max_votes:
                            # print('超额了', self.pk_op_votes - self.pk_me_votes,
                            #       self.user.pk_max_votes, self.pk_now_use, self.user.pk_max_votes)
                            continue
                        need = ((self.pk_op_votes-self.pk_me_votes)/self.user.pk_gift_rank)+5
                        gift_id = self.user.pk_gift_id  # 这个礼物是52分 20014
                        gift_num = need
                        print(f'赠送{need}个{self.user.pk_gift_id}')
                        # print(UtilsReq.send_gold, self.user, gift_id, gift_num, self._room_id, ruid)
                        self.pk_now_use += 52*need
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
                self.GIFT_QUEUE.put({
                    'room': room_id,
                    'username': username,
                    'uid': user_id,
                    'gift_name': gift_name,
                    'gift_num': int(gift_num),
                    't': time.time(),
                })

            elif cmd == 'GUARD_BUY':
                # user_id=data['data']['uid'],
                username = data['data']['username']
                gift_name = data['data']['gift_name']
                gift_num = data['data']['num']
                await self.send_danmu(self.user.gift_thx_format.format(username=username, num=gift_num, giftname=gift_name))

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
                # print(data)
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
                # print(data)
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
                # print(data)
                print('绝杀')
                t = data.get('timestamp')
                delay = data.get('data').get('timer')
                self.pk_end_time = t + delay + DELAY

            # 绝杀
            # {'cmd': 'PK_BATTLE_PRO_TYPE', 'pk_id': 748548, 'pk_status': 301, 'timestamp': 1582007539, 'data': {'timer': 60, 'final_hit_room_id': 3232493, 'be_final_hit_room_id': 21668541}}
            # 结束报告
            # {'cmd': 'PK_BATTLE_SETTLE_USER', 'pk_id': 748548, 'pk_status': 501, 'settle_status': 1, 'timestamp': 1582007599, 'data': {'pk_id': '748548', 'settle_status': 1, 'result_type': '3', 'battle_type': 0, 'result_info': {'total_score': 11, 'result_type_score': 10, 'pk_votes': 57052, 'pk_votes_name': '战力值', 'pk_crit_score': -1, 'pk_resist_crit_score': -1, 'pk_extra_score_slot': '每日20:00 ~ 23:00 ', 'pk_extra_value': 11410, 'pk_extra_score': 1, 'pk_task_score': 0, 'pk_times_score': 0, 'pk_done_times': 5, 'pk_total_times': 8, 'win_count': 1, 'win_final_hit': 1, 'winner_count_score': 0, 'task_score_list': []}, 'winner': {'room_id': 3232493, 'uid': 12461919, 'uname': '糕妹睡不醒', 'face': 'http://i1.hdslb.com/bfs/face/3a5ddcef155c9f5e5854e5d5b011aae17018576c.jpg', 'face_frame': '', 'exp': {'color': 5805790, 'user_level': 21, 'master_level': {'color': 10512625, 'level': 25}}, 'best_user': {'uid': 16821173, 'uname': '_饮马江湖风萧萧', 'face': 'http://i0.hdslb.com/bfs/face/00eaecb6da45fa072ff0cdef25a1f9d6fbc0571b.jpg', 'pk_votes': 57000, 'pk_votes_name': '战力值', 'exp': {'color': 6406234, 'level': 5}, 'face_frame': 'http://i0.hdslb.com/bfs/live/78e8a800e97403f1137c0c1b5029648c390be390.png', 'badge': {'url': 'http://i0.hdslb.com/bfs/live/b5e9ebd5ddb979a482421ca4ea2f8c1cc593370b.png', 'desc': '', 'position': 3}, 'award_info': None, 'award_info_list': [{'type': 1, 'bar_num': 4, 'bar_total': '6', 'get_status': 0, 'title': '每6次可获得', 'award_name': '时光沙漏', 'award_url': 'http://s1.hdslb.com/bfs/live/0898535576c195dd8b0c43c52a77276efb2a9aa1.png', 'num': 1, 'msg': '成为胜方最佳助攻6次可获得1枚', 'tips': '大乱斗中投喂可使主播本场免疫绝杀'}], 'end_win_award_info_list': {'list': []}}}, 'my_info': {'room_id': 3232493, 'uid': 12461919, 'uname': '糕妹睡不醒', 'face': 'http://i1.hdslb.com/bfs/face/3a5ddcef155c9f5e5854e5d5b011aae17018576c.jpg', 'face_frame': '', 'exp': {'color': 5805790, 'user_level': 21, 'master_level': {'color': 10512625, 'level': 25}}, 'best_user': {'uid': 16821173, 'uname': '_饮马江湖风萧萧', 'face': 'http://i0.hdslb.com/bfs/face/00eaecb6da45fa072ff0cdef25a1f9d6fbc0571b.jpg', 'pk_votes': 57000, 'pk_votes_name': '战力值', 'exp': {'color': 6406234, 'level': 5}, 'face_frame': 'http://i0.hdslb.com/bfs/live/78e8a800e97403f1137c0c1b5029648c390be390.png', 'badge': {'url': 'http://i0.hdslb.com/bfs/live/b5e9ebd5ddb979a482421ca4ea2f8c1cc593370b.png', 'desc': '', 'position': 3}, 'award_info': None, 'award_info_list': [{'type': 1, 'bar_num': 4, 'bar_total': '6', 'get_status': 0, 'title': '每6次可获得', 'award_name': '时光沙漏', 'award_url': 'http://s1.hdslb.com/bfs/live/0898535576c195dd8b0c43c52a77276efb2a9aa1.png', 'num': 1, 'msg': '成为胜方最佳助攻6次可获得1枚', 'tips': '大乱斗中投喂可使主播本场免疫绝杀'}], 'end_win_award_info_list': {'list': []}}}, 'level_info': {'first_rank_name': '小天才', 'second_rank_num': 2, 'first_rank_img': 'https://i0.hdslb.com/bfs/live/2eb2ffcc0c0a26d33ef2261c4ece5c9160ebcee0.png', 'second_rank_icon': 'https://i0.hdslb.com/bfs/live/a02cc5ae3c1dffe65c8a278075c542d7d495facb.png'}}}

            elif cmd in ['WELCOME_GUARD', 'WELCOME', 'NOTICE_MSG', 'SYS_GIFT', 'ACTIVITY_BANNER_UPDATE_BLS', 'ENTRY_EFFECT', 'ROOM_RANK', 'ACTIVITY_BANNER_UPDATE_V2', 'COMBO_END', 'ROOM_REAL_TIME_MESSAGE_UPDATE', 'ROOM_BLOCK_MSG', 'WISH_BOTTLE', 'WEEK_STAR_CLOCK', 'ROOM_BOX_MASTER', 'HOUR_RANK_AWARDS', 'ROOM_SKIN_MSG', 'RAFFLE_START', 'RAFFLE_END', 'GUARD_LOTTERY_START', 'GUARD_LOTTERY_END', 'GUARD_MSG', 'USER_TOAST_MSG', 'SYS_MSG', 'COMBO_SEND', 'ROOM_BOX_USER', 'TV_START', 'TV_END', 'ANCHOR_LOT_END', 'ANCHOR_LOT_AWARD', 'ANCHOR_LOT_CHECKSTATUS', 'ANCHOR_LOT_STAR', 'ROOM_CHANGE', 'LIVE', 'new_anchor_reward', 'room_admin_entrance', 'ROOM_ADMINS', 'PREPARING']:
                pass
            else:
                print(data)
        except:
            traceback.print_exc()
            print(data)
        return True


# {"code":0,"msg":"","message":"","data":{"id":4099580,"uname":"bishi","block_end_time":"2020-01-03 17:36:18"}}
# {'code': -400, 'msg': '此用户已经被禁言了', 'message': '此用户已经被禁言了', 'data': []}
