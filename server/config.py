# Webtiles server config for the decision-ladder prototype.
# Based on crawl's sample webserver/config.py and dcss-api's crawl-config/config.py.
# Game id "dcss-0.34" matches what dcss-api's scenario builder expects.

import collections
import logging
import os

server_path = os.path.dirname(os.path.abspath(__file__))

bind_nonsecure = True
bind_address = ""
bind_port = 8080
ssl_options = None

logging_config = {
    "level": logging.INFO,
    "format": "%(asctime)s %(levelname)s: %(message)s",
}

password_db = "/data/webserver/passwd.db3"
settings_db = "/data/webserver/user_settings.db3"
static_path = "/crawl/webserver/static"
template_path = "/crawl/webserver/templates/"

server_id = ""
game_data_no_cache = True
use_game_yaml = False

games = collections.OrderedDict([
    ("dcss-0.34", dict(
        version="0.34",
        name="Play 0.34",
        crawl_binary="/crawl/crawl",
        rcfile_path="/data/rcs/",
        macro_path="/data/rcs/",
        morgue_path="/data/rcs/%n",
        inprogress_path="/data/rcs/running",
        ttyrec_path="/data/rcs/ttyrecs/%n",
        socket_path="/data/rcs",
        client_path="/crawl/webserver/game_data/",
        morgue_url=None,
        show_save_info=True,
        allowed_with_hold=True,
        send_json_options=True,
        options=["-seed"],
    )),
])

dgl_status_file = "/data/rcs/status"
init_player_program = "/crawl/util/ladder-init-player.sh"
lobby_url = None

nick_regex = r"^[a-zA-Z0-9]{3,20}$"
max_passwd_length = 64
allow_password_reset = False

uid = None
gid = None
umask = None
chroot = None
pidfile = None
player_url = None
hup_reloads_config = True
autologin = None
