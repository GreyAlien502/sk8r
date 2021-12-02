#!/usr/bin/env python3
import os, textwrap, sys, re, argparse, collections, json, datetime, logging, builtins
class Namespace:
	def __init__(self,values):
		self._values = values
	def __getattr__(self,name):
		return self._values[name]
	def __setattr__(self,name,value):
		if name[0] == '_':#try:
			object.__setattr__(self, name, value)
		else:#except AttributeError:
			self._values[name] = value
	def __getitem__(self,name):
		return self._values[name]
	def __setitem_(self,name,value):
		self._values[name] = value
	def __str__(self):
		return json.dumps(self._values)
class arg:
	def __init__(self,*args,**kwargs):
		self.s = args
		self.kws = kwargs
def parse(args):
	parser = argparse.ArgumentParser()
	for arg in args:
		parser.add_argument(*arg.s,**arg.kws)
	return parser.parse_args()
def print(*args,**kwargs):
	builtins.print(*args,**dict(**kwargs,flush=True))


import socketio



# Start the connection process
options = parse([
	arg(
		'--tv',
		help='file to which to write new TV URLs',
		default=os.devnull,
	),
	arg(
		'--img',
		help='file to which to write new image URLs',
		default=os.devnull,
	),
	arg(
		'--verbose', '-v',
		action='store_true'
	),
	arg(
		'--username',
		help='username to connect as',
		default='guest',
	),
	arg(
		'--password',
		help='used to connect to Hue',
		default='guest',
	),
	arg(
		'--room',
		help='The user will be logged into the room on Hue with the given id.',
		default='main'
	),
	arg(
		'--server',
		help='the address of the server to which to connect',
		default='https://hue.merkoba.com',
	),
	arg(
		'--config',
		help=textwrap.dedent('''
			Options are read from FILE, which must be a JSON file.
			All options except 'config' itself can be set from FILE.
			Command line arguments overwrite options specified in FILE.
			
		'''),
		default=os.path.expanduser('~/.sk8r/config.json'),
	),
])
try:
	with open(options.config,'r') as config:
		options = Namespace({**options.__dict__,**json.load(config)})
except FileNotFoundError as e:...


# OUTPUT
def file_writer(filename):
	return lambda message: open(filename,'a').write(message+'\n')
tv = file_writer(options.tv)
img = file_writer(options.img)

debug = (
	(lambda x: (print(x), x)[-1])
	if options.verbose else
	(lambda x:x)
)



# INIT

# Centralized function to send emits to the Hue server
def hue_socket_emit(method, data):
	data['server_method_name'] = method
	hue_socket.emit(*debug(('server_method', data)))

# Removes unwanted formatting from Hue chat messages
def hue_clean_chat_message(message): #TODO
	return message.replace('/\=?\[dummy\-space\]\=?/gm, ')


def normalize_past_event(event):
	e = Namespace(event)
	e.data['date'] = e.date
	if e.type == 'chat':
		e.type = 'chat_message'
		e.data['message'] = e.data['content']
	if e.type == 'image':
		e.type = 'image_source_changed'
	if e.type == 'tv':
		e.type = 'tv_source_changed'
	return debug(e._values)

def handle(event,old=False):
	def print_action(date, user, message):
		print(
			f'''{
				datetime.datetime.fromtimestamp(date/1000)
			}	{
				user
			}	{
				message
			}'''
		)
	collections.defaultdict( lambda:print, dict(
		chat_message=lambda data:
			print_action(
				data.date,
				data.username,
				f''': {
					data.message
				} {
					data.link_title or ''
				} {
					'(edited)' if data.just_edited else ''
				}'''
			)
		,
		image_source_changed=lambda data:(
			source := (
				('https://hue.merkoba.com/static/room/'+options.room+'/image/' if data.type == 'upload' else '')
				+ data.source
			),
			img(source) if not old else...,
			print_action(data.date, data.setter,  f'''changed the image to { source }.'''),
			print_action(data.date, data.setter, ': '+data.comment) if data.comment else...,
		),
		tv_source_changed=lambda data:(
			source := (
				('https://hue.merkoba.com/static/room/'+options.room+'/tv/' if data.type == 'upload' else '')
				+ data.source
			),
			tv(source) if not old else...,
			print_action(data.date, data.setter,  f'''changed the TV to { source }.'''),
			print_action(data.date, data.setter, ': '+data.comment) if data.comment else...,
		),
		topic_change=lambda data:
			print(f'''The topic is now "{data.topic}".''')
		,
		user_joined=lambda data:
			print_action( data.date_joined, data.username, 'joined.')
			if 'options.show_joins' else
			...
		,
		user_disconnected=lambda data:
			print( data.username + ' disconnected.' )
			if 'config.show_joins' else
			...
		,
		joined=lambda data:(
			[
				handle(normalize_past_event(message),old=True)
				for message in data.log_messages
			],
			print(*( user['username'] for user in data.userlist )),
		),
		activity_trigger=lambda x:...,
		typing=lambda x:...,
		announcement=lambda x:...,
	) )[
		debug(event['type'])
	](
		Namespace(collections.defaultdict((lambda:None), debug(event['data']) ))
	)

# Object with all the supported Hue event handlers
# Each function receives a data object
hue_socket = socketio.Client()
hue_socket.on('update',lambda event:
	handle(event)
)
hue_socket.on('connect',lambda:(
		hue_socket_emit(
			'join_room',
			dict(
				alternative = True,
				room_id = options.room,
				username = options.username,
				password = options.password
			)
		),
		print(f'''I've connected you to {options.room} as {options.username}.''')
))
hue_socket.on('disconnect',lambda: (
	print(
		textwrap.dedent('''
			We've been disconnected!
		'''),
			#I'll try reconnecting...
		file=sys.stderr
	),
	#time.sleep(1),
))
hue_socket.connect(options.server)

for line in sys.stdin:
	if not line:
		continue

	command,_,data = re.search(r'^(/\S*|)(\s*)(.*)',line).groups()

	message_type,data_formatter = collections.defaultdict(
		lambda:( command, json.dumps ),
		{
			'' :( 'sendchat', lambda x: {'message':x} ),
			'/img' :( 'change_image_source', lambda x:{'src':x} ),
			'/tv' :( 'change_tv_source', lambda x:{'src':x} ),
		}
	)[command]

	try:
		hue_socket_emit(message_type, data_formatter(data))
	except Exception as e:
		logging.exception(e)

hue_socket.disconnect()
