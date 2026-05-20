import tinytuya

plug = tinytuya.OutletDevice('bf70a38629ee62797fw0gl', '192.168.0.12', r"""N3E]/2/xet>l'wSt""")
plug.set_version(3.5)
plug.set_socketTimeout(3)

print("...///....")
data = plug.turn_on(nowait=False)
print("%::", data)
