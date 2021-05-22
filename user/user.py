import asyncio
import json
from itertools import count
from typing import Callable, Optional

import conf_loader
import exceptions
import printer
from tasks.login import LoginTask
from web_session import WebSession

from .platform import AppPlatform, PcPlatform, TvPlatform


# user.toml 里面的东西全在self.dict_user里面，与 user 一一对应
# bili.toml 东西在 self.pc、self.app、self.tv 里面，因为这一串东西太复杂了，不方便在直接写在 User 里面了
class User:
    _ids = count(0)
    __slots__ = (
        'id', 'force_sleep', 'name', 'password', 'alias', 'task_ctrl',
        'task_arrangement', 'is_in_jail',

        'bililive_session', 'login_session', 'other_session',

        'dict_user', 'pc', 'app', 'tv', 'repost_del_lock',
        'dyn_lottery_friends',
        '_waiting_login', '_loop',

        ###
        'manage_room', 'alerts', 'gift_comb_delay', 'alert_second', 'gift_thx_format', 'focus_thx_format',
        'danmu_length', 'random_list_1', 'random_list_2', 'random_list_3',
        'medal_update_format', 'medal_update_check_delay',
        'guard_thx_format', 'fans_check_delay', 'only_live_thx',
        'silver_gift_thx_format', 'gold_gift_thx_format', 'disable_gift_thx',
        'reply', 'ban',
        'height', 'weight',
        'const_json', 'only_live_alert',
        'anchor_alert_format',
    )

    def __init__(
            self, dict_user: dict, task_ctrl: dict, task_arrangement: dict, dict_bili: dict, force_sleep: Callable):
        self.id = next(self._ids)
        self.force_sleep = force_sleep
        self.name = dict_user['username']
        self.password = dict_user['password']
        self.alias = dict_user.get('alias', self.name)
        self.task_ctrl = task_ctrl
        self.task_arrangement = task_arrangement
        self.is_in_jail = False  # 是否小黑屋
        ##
        self.manage_room = dict_user['manage_room']
        self.alerts = dict_user.get('alerts', [])
        self.gift_comb_delay = dict_user['gift_comb_delay']
        self.alert_second = dict_user['alert_second']
        self.gift_thx_format = dict_user.get('gift_thx_format', '感谢{username}投喂的{giftname}x{num}')
        self.silver_gift_thx_format = dict_user.get('silver_gift_thx_format', self.gift_thx_format)
        self.gold_gift_thx_format = dict_user.get('gold_gift_thx_format', self.gift_thx_format)
        self.focus_thx_format = dict_user['focus_thx_format']
        self.guard_thx_format = dict_user.get('guard_thx_format', self.gift_thx_format)
        self.danmu_length = dict_user.get('danmu_length', 30)
        self.medal_update_format = dict_user.get('medal_update_format', '')
        self.medal_update_check_delay = dict_user.get('medal_update_check_delay', 30)
        self.only_live_thx = dict_user.get('only_live_thx', False)
        self.only_live_alert = dict_user.get('only_live_alert', True)
        self.anchor_alert_format = dict_user.get('anchor_alert_format', '')
        self.reply = dict_user.get('reply', [])
        self.ban = dict_user.get('ban', [])
        self.height = dict_user.get('height', 0)
        self.weight = dict_user.get('weight', 0)
        self.disable_gift_thx = dict_user.get('disable_gift_thx', False)

        if dict_user.get('const_json'):
            self.const_json = json.load(open(dict_user.get('const_json'), 'r'))
        else:
            self.const_json = {}

        self.fans_check_delay = dict_user.get('fans_check_delay', 20)

        self.random_list_1 = dict_user.get('random_list_1', [])
        self.random_list_2 = dict_user.get('random_list_2', [])
        self.random_list_3 = dict_user.get('random_list_3', [])
        if len(self.random_list_1) == 0:
            self.random_list_1 = [""]
        if len(self.random_list_2) == 0:
            self.random_list_2 = [""]
        if len(self.random_list_3) == 0:
            self.random_list_3 = [""]
        ##
        self.bililive_session = WebSession()
        self.login_session = WebSession()
        self.other_session = WebSession()

        # 每个user里面都分享了同一个dict，必须要隔离，否则更新cookie这些的时候会互相覆盖
        self.pc = PcPlatform(dict_bili['pc_headers'].copy())
        self.app = AppPlatform(dict_bili['app_headers'].copy(), dict_bili['app_params'])
        self.tv = TvPlatform(dict_bili['tv_headers'].copy(), dict_bili['tv_params'])

        self.dict_user = dict_user

        self.update_login_data(dict_user)

        self._waiting_login = None
        self._loop = asyncio.get_event_loop()

        self.repost_del_lock = asyncio.Lock()  # 在follow与unfollow过程中必须保证安全(repost和del整个过程加锁)
        dyn_lottery_friends = [(str(uid), name) for uid, name in task_ctrl['dyn_lottery_friends'].items()]
        self.dyn_lottery_friends = dyn_lottery_friends  # list (uid, name)

    def update_login_data(self, login_data):
        for key, value in login_data.items():
            self.dict_user[key] = value
            if key == 'cookie':
                self.pc.update_cookie(value)
                self.app.update_cookie(value)
                self.tv.update_cookie(value)
        conf_loader.write_user(login_data, self.id)

    def is_online(self):
        return self.pc.headers['cookie'] and self.app.headers['cookie'] and self.tv.headers['cookie']

    def update_log(self):
        conf_loader.write_user({'weight': self.weight, 'height': self.height}, self.id)

    def info(
            self,
            *objects,
            with_userid=True,
            **kwargs):
        if with_userid:
            printer.info(
                *objects,
                **kwargs,
                extra_info=f'用户id:{self.id} 名字:{self.alias}')
        else:
            printer.info(*objects, **kwargs)

    def warn(self, *objects, **kwargs):
        printer.warn(
            *objects,
            **kwargs,
            extra_info=f'用户id:{self.id} 名字:{self.alias}')

    def app_sign(self, extra_params: Optional[dict] = None) -> dict:
        return self.app.sign(extra_params)

    def tv_sign(self, extra_params: Optional[dict] = None) -> dict:
        return self.tv.sign(extra_params)

    async def req_s(self, func, *args, timeout=None):
        while True:
            if self._waiting_login is None:
                try:
                    return await asyncio.wait_for(func(*args), timeout=timeout)
                except asyncio.TimeoutError:
                    self.info(f'TASK {func} 请求超时，即将 CANCEL')
                    raise asyncio.CancelledError()
                except exceptions.LogoutError:  # logout
                    if self._waiting_login is None:  # 当前没有处理的运行
                        self.info('判定出现了登陆失败，且未处理')
                        self._waiting_login = self._loop.create_future()
                        try:
                            await LoginTask.handle_login_status(self)
                            self.info('已经登陆了')
                        except asyncio.CancelledError:  # 登陆中取消，把waiting_login设置，否则以后的req会一直堵塞
                            raise
                        finally:
                            self._waiting_login.set_result(-1)
                            self._waiting_login = None
                    else:  # 已有处理的运行了
                        self.info('判定出现了登陆失败，已经处理')
                        await self._waiting_login
                except exceptions.ForbiddenError:
                    await asyncio.shield(self.force_sleep(3600))  # bili_sched.force_sleep
                    await asyncio.sleep(3600)  # 有的function不受sched控制，主动sleep即可，不cancel原因是怕堵死一些协程
            else:
                await self._waiting_login

    def fall_in_jail(self):
        self.is_in_jail = True
        self.info(f'用户进入小黑屋')

    def out_of_jail(self):
        self.is_in_jail = False
        self.info(f'抽奖脚本尝试性设置用户已出小黑屋（如果实际没出还会再判定进去）')

    def print_status(self):
        jail_status = '恭喜中奖' if self.is_in_jail else '自由之身'
        self.info('当前用户的状态：', jail_status)
