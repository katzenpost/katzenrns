# Using katzenrns

katzenrns needs a Reticulum instance with a path to a Pigeonhole replica. There are two ways to
have one, and the choice is only about Reticulum; the chat is the same in both.

## With your own rnsd

If you run Reticulum already, katzenrns attaches to it like any other Reticulum program: the
instance `~/.reticulum` describes, which is your running `rnsd`, or one katzenrns starts from
that config when none is running. The replica has to be reachable from that instance. For the
bridge replica on windfall2, which joins the mesh to the
[namenlos](https://katzenpost.network) mixnet, that is one TCP client interface in
`~/.reticulum/config`, after which rnsd is restarted:

    [interfaces]
      [[namenlos bridge replica]]
        type = TCPClientInterface
        enabled = yes
        target_host = 162.220.11.225
        target_port = 4242

Then:

    katzenrns                           # the desktop client
    katzenrns --headless --name bob     # commands on stdin, for scripts

A Reticulum instance that already reaches the replica some other way, through a transport node
that peers with it, needs no edit at all. `--config DIR` points katzenrns at a Reticulum config
directory other than `~/.reticulum`.

## Without Reticulum of your own

If you have never run Reticulum and only want to reach a replica on the internet, give its
address and nothing else:

    katzenrns --replica 162.220.11.225:4242
    katzenrns --replica 162.220.11.225:4242 --headless --name bob

katzenrns then starts a Reticulum instance of its own, with one TCP link to that replica, from a
config it writes under its state directory (`~/.local/share/katzenrns/reticulum/config`). That
instance is private to katzenrns: it does not touch `~/.reticulum`, and it is not shared with
other Reticulum programs, so a running rnsd and this instance coexist without seeing each other.
`--replica` and `--config` are the two ways to reach the mesh; give one.

## Options

The status bar reads "On the mesh" within about twenty seconds, once the replica has announced.
The box size defaults to namenlos's, 1549 bytes; a mesh of its own with another size sets
`--box-size`. Boxes are read at any allowed size: that one, namenlos's and the mesh's.

`--wire-version 3|4|5` picks the katzenqt1 wire version this client writes and mints: 3 is the
version 3 map form with long vouchers, for peers that read only that; 4, the default, is the
compact form; 5 also packs queued messages into one box. katzenqt, jam and frank_chat read only
versions 3 and 4 and show a version 5 message only as a notice that it cannot be shown, so 5 is
for groups whose members all run katzenrns or hushphone. katzenrns reads all three. A message
this client cannot read, of a newer version or an unknown type, is shown as a notice asking to
update the app.

`--query-mode auto|request|channel` picks how queries reach a replica, one of the two
[query modes](https://github.com/katzenpost/pigeonhole_rns#query-modes) a replica serves:
`request` sends Link requests, with Resources for large queries; `channel` sends Channel messages,
for replicas on Reticulum stacks without requests, such as Reticulum-rs, and uses only replicas
that announce Channel support. `auto`, the default, starts with requests. If a replica announces
Channel support but does not answer requests, it falls back to Channel and keeps using Channel
for that replica.

`katzenrns --help` lists the rest.

## The desktop client

The first launch asks for the name you show others. Then: **Create a group**, or **Join a
group**, which shows a voucher code to send to someone already in the group; they paste it into
**Add someone**. The code is the same text katzenqt uses, so a katzenqt user can add you, and
you them. It is also shown as the QR code hushphone, the T-Deck and katzenqt draw for it, module
for module.

## The headless shell

The headless shell takes `create g`, `join g`, `invite g CODE`, `send g text`, `show g`,
`members g`, `scan g`, `remove g NAME`, `leave g` and prints `READY`, `VOUCHER=...`
(followed by the code as a QR in Unicode half blocks), `JOINED g` and `LINE g who: text` as
things happen.

## Release binaries

Each release on the [releases page](https://github.com/katzenpost/katzenrns/releases) has a
single-file Linux executable, `katzenrns-VERSION-linux-x86_64`, with Python, Reticulum, Qt and
the rest inside, built on Ubuntu 22.04 to run on distributions with glibc 2.35 or newer; and the
wheel and source archive. To verify and run one, with the files and `SHA256SUMS` in one
directory:

    sha256sum --check --ignore-missing SHA256SUMS
    chmod +x katzenrns-VERSION-linux-x86_64
    ./katzenrns-VERSION-linux-x86_64 --replica 162.220.11.225:4242

It takes the same options as `katzenrns`. The desktop client uses the OpenGL and X11 libraries
a desktop already has; the headless shell needs none.
