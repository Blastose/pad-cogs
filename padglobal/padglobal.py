import csv
import difflib
import io
from collections import defaultdict

import prettytable
from redbot.core import checks
from redbot.core import commands

import rpadutils.rpadutils
from rpadutils.rpadutils import *

global PADGLOBAL_COG

DATA_EXPORT_PATH = 'data/padglobal/pad global_data.json'

PAD_CMD_HEADER = """
PAD Global Commands
^pad      : general command list
^padfaq   : FAQ command list
^boards   : optimal boards
^glossary : common PAD definitions
^boss     : boss mechanics
^which    : which monster evo info
"""

BLACKLISTED_CHARACTERS = '^[]*`~_'

PORTRAIT_TEMPLATE = 'https://storage.googleapis.com/mirubot/padimages/{}/portrait/{}.png'

DISABLED_MSG = 'PAD Global info disabled on this server'

FARMABLE_MSG = 'This monster is **farmable** so make as many copies of whichever evos you like.'
MP_BUY_MSG = ('This monster can be purchased with MP. **DO NOT** buy MP cards without a good reason'
              ', check ^mpdra? for specific recommendations.')
SIMPLE_TREE_MSG = 'This monster appears to be uncontroversial; use the highest evolution.'


def is_padglobal_admin_check(ctx):
    return checks.is_owner() or PADGLOBAL_COG.settings.checkAdmin(ctx.author.id)


def is_padglobal_admin():
    return commands.check(is_padglobal_admin_check)


def lookup_named_monster(query: str):
    padinfo_cog = PADGLOBAL_COG.bot.get_cog('PadInfo')
    if padinfo_cog is None:
        raise Exception("Cog not Loaded")
    nm, err, debug_info = padinfo_cog._findMonster(query)
    return nm, err, debug_info


def monster_no_to_monster(monster_no):
    padinfo_cog = PADGLOBAL_COG.bot.get_cog('PadInfo')
    if padinfo_cog is None:
        return None
    return padinfo_cog.get_monster_by_no(monster_no)


class PadGlobal(commands.Cog):
    """Global PAD commands."""

    def __init__(self, bot):
        global PADGLOBAL_COG
        PADGLOBAL_COG = self
        self.bot = bot
        self.file_path = "data/padglobal/commands.json"
        with open("data/padglobal/commands.json", "a+") as f:
            f.seek(0)
            self.c_commands = json.load(f)
        self.settings = PadGlobalSettings("padglobal")

        self._export_data()

    def _export_data(self):

        faq_and_boards = self.settings.faq() + self.settings.boards()
        general = {k: v for k, v in self.c_commands.items() if k not in faq_and_boards}
        faq = {k: v for k, v in self.c_commands.items() if k in self.settings.faq()}
        boards = {k: v for k, v in self.c_commands.items() if k in self.settings.boards()}
        glossary = self.settings.glossary()
        bosses = self.settings.boss()
        which = self.settings.which()
        dungeon_guide = self.settings.dungeonGuide()
        leader_guide = self.settings.leaderGuide()

        results = {
            'general': general,
            'faq': faq,
            'boards': boards,
            'glossary': glossary,
            'boss': bosses,
            'which': which,
            'dungeon_guide': dungeon_guide,
            'leader_guide': leader_guide,
        }

        with open(DATA_EXPORT_PATH, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4)

    @commands.command()
    @is_padglobal_admin()
    async def breakglass(self, ctx, *, reason: str):
        """Shuts down the bot, for emergency use only.

        If the bot needs to be restarted in an emergency, you can use this to do it.
        Since the bot automatically restarts after being shut down for 30s, this
        command just kills the bot.

        Obviously this will only work if the bot can read messages, but there is a
        class of problems where the bot can read messages but not respond, so this
        could handle those cases.
        """
        msg = '------------------------\n'
        msg += '{} shut down the bot because: {}\n'.format(ctx.author.name, reason)
        msg += '------------------------\n'
        print(msg)

        try:
            app_info = await self.bot.application_info()
            owner = app_info.owner
            await owner.send(msg)
            await ctx.send("Owner has been notified, shutting down...")
        except Exception as ex:
            print('Failed to notifiy for breakglass: ' + str(ex))

        await self.bot.shutdown()

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def togglepadglobal(self, ctx):
        """Enable or disable PAD Global commands for the server."""
        server_id = ctx.guild.id
        if server_id in self.settings.disabledServers():
            self.settings.rmDisabledServer(server_id)
        else:
            self.settings.addDisabledServer(server_id)
        status = 'disabled' if self.settings.checkDisabled(ctx) else 'enabled'
        await ctx.send(inline('PAD Global commands {} on this server').format(status))

    async def _check_disabled(self, ctx):
        """If the server is disabled, print a warning and return True"""
        if self.settings.checkDisabled(ctx):
            msg = await ctx.send(inline(DISABLED_MSG))
            await asyncio.sleep(3)
            await msg.delete_messasge()
            return True
        return False

    @commands.command()
    @is_padglobal_admin()
    async def debugiddump(self, ctx):
        padinfo_cog = self.bot.get_cog('PadInfo')
        mi = padinfo_cog.index_all

        async def write_send(nn_map, file_name):
            data_holder = io.StringIO()
            writer = csv.writer(data_holder)
            for nn, nm in nn_map.items():
                writer.writerow([nn, nm.monster_no_na, nm.name_na])
            bytes_data = io.BytesIO(data_holder.getvalue().encode())
            await ctx.channel.send(file=discord.File(bytes_data, file_name))

        await write_send(mi.all_entries, 'all_entries.csv')
        await write_send(mi.two_word_entries, 'two_word_entries.csv')

    @commands.command()
    @is_padglobal_admin()
    async def debugid(self, ctx, *, query):
        padinfo_cog = PADGLOBAL_COG.bot.get_cog('PadInfo')
        # m is a named monster
        m, err, debug_info = lookup_named_monster(query)

        if m is None:
            await ctx.send(box('No match: ' + err))
            return

        msg = "{}. {}".format(m.monster_no_na, m.name_na)
        msg += "\nLookup type: {}".format(debug_info)

        def list_or_none(l):
            if len(l) == 1:
                return '\n\t{}'.format(''.join(l))
            elif len(l):
                return '\n\t' + '\n\t'.join(sorted(l))
            else:
                return 'NONE'

        msg += "\n\nNickname original components:"
        msg += "\n monster_basename: {}".format(m.monster_basename)
        msg += "\n group_computed_basename: {}".format(m.group_computed_basename)
        msg += "\n extra_nicknames: {}".format(list_or_none(m.extra_nicknames))

        msg += "\n\nNickname final components:"
        msg += "\n basenames: {}".format(list_or_none(m.group_basenames))
        msg += "\n prefixes: {}".format(list_or_none(m.prefixes))

        msg += "\n\nAccepted nickname entries:"
        accepted_nn = list(filter(lambda nn: m.monster_id == padinfo_cog.index_all.all_entries[nn].monster_id,
                                  m.final_nicknames))
        accepted_twnn = list(filter(lambda nn: m.monster_id == padinfo_cog.index_all.two_word_entries[nn].monster_id,
                                    m.final_two_word_nicknames))

        msg += "\n nicknames: {}".format(list_or_none(accepted_nn))
        msg += "\n two_word_nicknames: {}".format(list_or_none(accepted_twnn))

        msg += "\n\nOverwritten nickname entries:"
        replaced_nn = list(filter(lambda nn: nn not in accepted_nn,
                                  m.final_nicknames))

        replaced_twnn = list(filter(lambda nn: nn not in accepted_twnn,
                                    m.final_two_word_nicknames))

        replaced_nn_info = map(lambda nn: (
            nn, padinfo_cog.index_all.all_entries[nn]), replaced_nn)
        replaced_twnn_info = map(
            lambda nn: (nn, padinfo_cog.index_all.two_word_entries[nn]), replaced_twnn)

        replaced_nn_text = list(map(lambda nn_info: '{} : {}. {}'.format(
            nn_info[0], nn_info[1].monster_no_na, nn_info[1].name_na),
                                    replaced_nn_info))

        replaced_twnn_text = list(map(lambda nn_info: '{} : {}. {}'.format(
            nn_info[0], nn_info[1].monster_no_na, nn_info[1].name_na),
                                      replaced_twnn_info))

        msg += "\n nicknames: {}".format(list_or_none(replaced_nn_text))
        msg += "\n two_word_nicknames: {}".format(list_or_none(replaced_twnn_text))

        msg += "\n\nNickname entry sort parts:"
        msg += "\n (is_low_priority, group_size, monster_no_na) : ({}, {}, {})".format(
            m.is_low_priority, m.group_size, m.monster_no_na)

        msg += "\n\nMatch selection sort parts:"
        msg += "\n (is_low_priority, rarity, monster_no_na) : ({}, {}, {})".format(
            m.is_low_priority, m.rarity, m.monster_no_na)

        sent_messages = []
        for page in pagify(msg):
            sent_messages.append(await ctx.send(box(page)))
        await rpadutils.await_and_remove(self.bot, sent_messages[-1], ctx.author,
                                         delete_msgs=sent_messages, timeout=30)

    @commands.command()
    @is_padglobal_admin()
    async def forceindexreload(self, ctx):
        await ctx.send('starting reload')
        dadguide_cog = self.bot.get_cog('Dadguide')
        await dadguide_cog.reload_config_files()
        padinfo_cog = self.bot.get_cog('PadInfo')
        await padinfo_cog.refresh_index()
        await ctx.send('finished reload')

    @commands.group()
    @is_padglobal_admin()
    async def padglobal(self, ctx):
        """PAD global custom commands."""
        if ctx.invoked_subcommand is None:
            # await ctx.send_help()
            pass

    @padglobal.command()
    async def say(self, ctx, *, text: str):
        """Test a padglobal command with emoji replacements."""
        text = replace_emoji_names_with_code(self._get_emojis(), text)
        await ctx.send(text)

    @padglobal.command()
    async def add(self, ctx, command: str, *, text: str):
        """Adds a PAD global command

        Example:
        !padglobal add command_name Text you want
        """
        command = command.lower()
        text = clean_global_mentions(text)
        text = text.replace(u'\u200b', '')
        text = replace_emoji_names_with_code(self._get_emojis(), text)
        if command in self.bot.all_commands.keys():
            await ctx.send("That is already a standard command.")
            return

        for c in BLACKLISTED_CHARACTERS:
            if c in command:
                await ctx.send("Invalid character in name: {}".format(c))
                return

        if not self.c_commands:
            self.c_commands = {}

        op = 'EDITED' if command in self.c_commands else 'ADDED'
        self.c_commands[command] = text
        json.dump(self.c_commands, open(self.file_path, 'w+'))
        await ctx.send("PAD command successfully {}.".format(op))

    @padglobal.command()
    async def delete(self, ctx, command: str):
        """Deletes a PAD global command

        Example:
        !padglobal delete yourcommand"""
        command = command.lower()
        cmdlist = self.c_commands
        if command in cmdlist:
            cmdlist.pop(command, None)
            json.dump(self.c_commands, open(self.file_path, 'w+'))
            await ctx.send("PAD command successfully deleted.")
        else:
            await ctx.send("PAD command doesn't exist.")

    @padglobal.command()
    async def setgeneral(self, ctx, command: str):
        """Sets a command to show up in ^pad (the default).

        Example:
        ^padglobal setgeneral yourcommand"""
        command = command.lower()
        if command not in self.c_commands:
            await ctx.send("PAD command doesn't exist.")
            return

        self.settings.setGeneral(command)
        await ctx.send("PAD command set to general.")

    @padglobal.command()
    async def setfaq(self, ctx, command: str):
        """Sets a command to show up in ^padfaq.

        Example:
        ^padglobal setfaq yourcommand"""
        command = command.lower()
        if command not in self.c_commands:
            await ctx.send("PAD command doesn't exist.")
            return

        self.settings.setFaq(command)
        await ctx.send("PAD command set to faq.")

    @padglobal.command()
    async def setboards(self, ctx, command: str):
        """Sets a command to show up in ^boards.

        Example:
        ^padglobal setboards yourcommand"""
        command = command.lower()
        if command not in self.c_commands:
            await ctx.send("PAD command doesn't exist.")
            return

        self.settings.setBoards(command)
        await ctx.send("PAD command set to boards.")

    @padglobal.command()
    async def checktype(self, ctx, command: str):
        """Checks if a command is board, FAQ, or general"""
        command = command.lower()
        if command in self.settings.boards():
            await ctx.send('{} is a board.'.format(command))
        elif command in self.settings.faq():
            await ctx.send('{} is a FAQ.'.format(command))
        elif command in self.c_commands:
            await ctx.send('{} is a general padglobal command.'.format(command))
        else:
            await ctx.send('{} is not a padglobal command. It might be a meme or a custom command.'.format(command))

    @commands.command()
    async def pad(self, ctx):
        """Shows PAD global command list"""
        if await self._check_disabled(ctx):
            return
        configured = self.settings.faq() + self.settings.boards()
        cmdlist = {k: v for k, v in self.c_commands.items() if k not in configured}
        await self.print_cmdlist(ctx, cmdlist)

    @commands.command()
    async def padfaq(self, ctx):
        """Shows PAD FAQ command list"""
        if await self._check_disabled(ctx):
            return
        cmdlist = {k: v for k, v in self.c_commands.items() if k in self.settings.faq()}
        await self.print_cmdlist(ctx, cmdlist)

    @commands.command()
    async def boards(self, ctx):
        """Shows PAD Boards command list"""
        if await self._check_disabled(ctx):
            return
        cmdlist = {k: v for k, v in self.c_commands.items() if k in self.settings.boards()}
        await self.print_cmdlist(ctx, cmdlist)

    async def print_cmdlist(self, ctx, cmdlist, inline=False):
        if not cmdlist:
            await ctx.send("There are no padglobal commands yet")
            return

        cmds = list(cmdlist.keys())
        prefixes = defaultdict(int)

        for c in cmds:
            m = re.match(r'^([a-zA-Z]+)\d+$', c)
            if m:
                grp = m.group(1)
                prefixes[grp] = prefixes[grp] + 1

        good_prefixes = [cmd for cmd, cnt in prefixes.items() if cnt > 1]
        prefix_to_suffix = defaultdict(list)
        prefix_to_other = defaultdict(list)

        i = 0
        msg = PAD_CMD_HEADER + "\n"

        if inline:
            for cmd in sorted([cmd for cmd in cmdlist.keys()]):
                msg += " {} : {}\n".format(cmd, cmdlist[cmd])
            for page in pagify(msg):
                await ctx.author.send(box(page))
            return

        for cmd in sorted([cmd for cmd in cmdlist.keys()]):
            m = re.match(r'^([a-zA-Z]+)(\d+)$', cmd)
            if m:
                prefix = m.group(1)
                if prefix in good_prefixes:
                    suffix = m.group(2)
                    prefix_to_suffix[prefix].append(suffix)
                    continue

            should_skip = False
            for good_prefix in good_prefixes:
                if cmd.startswith(good_prefix):
                    prefix_to_other[prefix].append(cmd)
                    should_skip = True
                    break
            if should_skip:
                continue

            msg += " {}{}\n".format(ctx.prefix, cmd)

        if prefix_to_suffix:
            msg += "\nThe following commands are indexed:\n"
            for prefix in sorted(prefix_to_suffix.keys()):
                msg += " {}{}[n]:\n  ".format(ctx.prefix, prefix)

                for suffix in sorted(map(int, prefix_to_suffix[prefix])):
                    msg += " {}{}".format(prefix, suffix)

                if len(prefix_to_other[prefix]):
                    msg += "\n"
                    for cmd in sorted(prefix_to_other[prefix]):
                        msg += " {}{}".format(ctx.prefix, cmd)
                msg += "\n\n"

        for page in pagify(msg):
            await ctx.author.send(box(page))

    @commands.command()
    async def glossaryto(self, ctx, to_user: discord.Member, *, term: str):
        """Send a user a glossary entry

        ^glossaryto @tactical_retreat godfest
        """
        if await self._check_disabled(ctx):
            return
        corrected_term, result = self.lookup_glossary(term)
        await self._do_send_term(ctx, to_user, term, corrected_term, result)

    @commands.command()
    async def padto(self, ctx, to_user: discord.Member, *, term: str):
        """Send a user a pad/padfaq entry

        ^padto @tactical_retreat jewels?
        """
        if await self._check_disabled(ctx):
            return
        corrected_term = self._lookup_command(term)
        result = self.c_commands.get(corrected_term, None)
        await self._do_send_term(ctx, to_user, term, corrected_term, result)

    async def _do_send_term(self, ctx, to_user: discord.Member, term, corrected_term, result):
        """Does the heavy lifting shared by padto and glossaryto."""
        if result:
            result_output = '**{}** : {}'.format(corrected_term, result)
            result = "{} asked me to send you this:\n{}".format(
                ctx.author.name, result_output)
            await to_user.send(result)
            msg = "Sent that info to {}".format(to_user.name)
            if term != corrected_term:
                msg += ' (corrected to {})'.format(corrected_term)
            await ctx.send(inline(msg))
        else:
            await ctx.send(inline('No definition found'))

    @commands.command()
    async def glossary(self, ctx, *, term: str = None):
        """Shows PAD Glossary entries"""
        if await self._check_disabled(ctx):
            return

        if term:
            term, definition = self.lookup_glossary(term)
            if definition:
                definition_output = '**{}** : {}'.format(term, definition)
                await ctx.send(definition_output)
            else:
                await ctx.send(inline('No definition found'))
            return

        msg = self.glossary_to_text()
        for page in pagify(msg):
            await ctx.author.send(page)

    def glossary_to_text(self):
        glossary = self.settings.glossary()
        msg = '__**PAD Glossary terms (also check out ^pad / ^padfaq / ^boards / ^which)**__'
        for term in sorted(glossary.keys()):
            definition = glossary[term]
            msg += '\n**{}** : {}'.format(term, definition)
        return msg

    def lookup_glossary(self, term):
        glossary = self.settings.glossary()
        term = term.lower()
        definition = glossary.get(term, None)

        if definition:
            return term, definition

        matches = self._get_corrected_cmds(term, glossary.keys())

        if not matches:
            matches = difflib.get_close_matches(term, glossary.keys(), n=1, cutoff=.8)

        if not matches:
            return term, None
        else:
            term = matches[0]
            return term, glossary[term]

    @padglobal.command()
    async def addglossary(self, ctx, term, *, definition):
        """Adds a term to the glossary.
        If you want to use a multiple word term, enclose it in quotes.

        e.x. ^padglobal addglossary alb Awoken Liu Bei
        e.x. ^padglobal addglossary "never dathena" NA will never get dathena
        """
        term = term.lower()
        definition = clean_global_mentions(definition)
        definition = definition.replace(u'\u200b', '')
        definition = replace_emoji_names_with_code(self._get_emojis(), definition)

        op = 'EDITED' if term in self.settings.glossary() else 'ADDED'
        self.settings.addGlossary(term, definition)
        await ctx.send("PAD glossary term successfully {}.".format(op))

    @padglobal.command()
    async def rmglossary(self, ctx, *, term):
        """Removes a term from the glossary."""
        term = term.lower()
        if term not in self.settings.glossary():
            await ctx.send("Glossary item doesn't exist.")
            return

        self.settings.rmGlossary(term)
        await ctx.send("done")

    @commands.command()
    async def boss(self, ctx, *, term: str = None):
        """Shows boss skill entries"""
        if await self._check_disabled(ctx):
            return
        if term:
            term_new, definition = self.lookup_boss(term)
            if definition:
                if term_new != term.lower():
                    await ctx.send('No entry for {} found, corrected to {}'.format(term, term_new))
                await ctx.send(definition)
            else:
                await ctx.send(inline('No mechanics found'))
            return
        msg = self.boss_to_text()
        for page in pagify(msg):
            await ctx.author.send(page)

    @commands.command()
    async def bosslist(self, ctx):
        """Shows boss skill entries"""
        if await self._check_disabled(ctx):
            return
        msg = self.boss_to_text_index()
        for page in pagify(msg):
            await ctx.author.send(page)

    def lookup_boss(self, term):
        bosses = self.settings.boss()
        term = term.lower()
        definition = bosses.get(term, None)
        if definition:
            return term, definition
        matches = self._get_corrected_cmds(term, bosses.keys())

        if not matches:
            matches = difflib.get_close_matches(term, bosses.keys(), n=1, cutoff=.8)

        if not matches:
            return term, None
        else:
            term = matches[0]
            return term, bosses[term]

    def boss_to_text(self):
        bosses = self.settings.boss()
        msg = '__**PAD Boss Mechanics (also check out ^pad / ^padfaq / ^boards / ^which /^glossary)**__'
        for term in sorted(bosses.keys()):
            definition = bosses[term]
            msg += '\n**{}**\n{}'.format(term, definition)
        return msg

    def boss_to_text_index(self):
        bosses = self.settings.boss()
        msg = '__**Available PAD Boss Mechanics (also check out ^pad / ^padfaq / ^boards / ^which /^glossary)**__'
        msg = msg + '\n' + ',\n'.join(sorted(bosses.keys()))
        return msg

    @padglobal.command()
    async def addboss(self, ctx, term, *, definition):
        """Adds a set of boss mechanics.
        If you want to use a multiple word boss name, enclose it in quotes."""
        term = term.lower()
        op = 'EDITED' if term in self.settings.boss() else 'ADDED'
        definition = clean_global_mentions(definition)
        definition = definition.replace(u'\u200b', '')
        definition = replace_emoji_names_with_code(self._get_emojis(), definition)
        self.settings.addBoss(term, definition)
        await ctx.send("PAD boss mechanics successfully {}.".format(op))

    @padglobal.command()
    async def rmboss(self, ctx, *, term):
        """Adds a set of boss mechanics."""
        term = term.lower()
        if term not in self.settings.boss():
            await ctx.send("Boss mechanics item doesn't exist.")
            return

        self.settings.rmBoss(term)
        await ctx.send("done")

    @commands.command()
    async def which(self, ctx, *, term: str = None):
        """Shows PAD Which Monster entries"""
        if await self._check_disabled(ctx):
            return

        if term is None:
            await ctx.author.send('__**PAD Which Monster**__ *(also check out ^pad / ^padfaq / ^boards / ^glossary)*')
            msg = self.which_to_text()
            for page in pagify(msg):
                await ctx.author.send(box(page))
            return

        name, definition = await self._resolve_which(ctx, term)
        if name is None or definition is None:
            return
        await ctx.send(inline('Which {}'.format(name)))
        await ctx.send(definition)

    async def _resolve_which(self, ctx, term):
        term = term.lower().replace('?', '')
        nm, _, _ = lookup_named_monster(term)
        if nm is None:
            await ctx.send(inline('No monster matched that query'))
            return None, None

        name = nm.group_computed_basename.title()
        definition = self.settings.which().get(str(nm.base_monster_no), None)

        if definition is not None:
            return name, definition

        monster = monster_no_to_monster(nm.base_monster_no)

        if monster.mp_evo:
            return name, MP_BUY_MSG
        elif monster.farmable_evo:
            return name, FARMABLE_MSG
        elif check_simple_tree(monster):
            return name, SIMPLE_TREE_MSG
        else:
            await ctx.send(inline('No which info for {}'.format(name)))
            return None, None

    @commands.command()
    async def whichto(self, ctx, to_user: discord.Member, *, term: str):
        """Send a user a which monster entry.

        ^whichto @tactical_retreat saria
        """
        if await self._check_disabled(ctx):
            return

        name, definition = await self._resolve_which(ctx, term)
        if name is None or definition is None:
            return
        await self._do_send_which(ctx, to_user, name, definition)

    def which_to_text(self):
        items = list()
        monsters = defaultdict(list)
        for w in self.settings.which():
            if w.isdigit():
                nm, _, _ = lookup_named_monster(w)
                name = nm.group_computed_basename.title()
                m = monster_no_to_monster(nm.monster_id)
                grp = m.series.name
                monsters[grp].append(name)
            else:
                items.append(w)

        msg = '\nGeneral:\n{}'.format(', '.join(sorted(items)))

        tbl = prettytable.PrettyTable(['Group', 'Members'])
        tbl.hrules = prettytable.HEADER
        tbl.vrules = prettytable.NONE
        tbl.align = "l"
        for grp in sorted(monsters.keys()):
            tbl.add_row([grp, ', '.join(sorted(monsters[grp]))])

        tbl_string = rpadutils.strip_right_multiline(tbl.get_string())
        msg += '\n\n{}'.format(tbl_string)

        return msg

    async def _do_send_which(self, ctx, to_user: discord.Member, name, definition):
        """Does the heavy lifting for whichto."""
        result_output = '**Which {}**\n{}'.format(name, definition)
        result = "{} asked me to send you this:\n{}".format(
            ctx.author.name, result_output)
        await to_user.send(result)
        msg = "Sent info on {} to {}".format(name, to_user.name)
        await ctx.send(inline(msg))

    @padglobal.command()
    async def addwhich(self, ctx, monster_id: int, *, definition):
        """Adds an entry to the which monster evo list.

        If you provide a monster ID, the term will be entered for that monster tree.
        e.x. ^padglobal addwhich 3818 take the pixel one
        """
        m = monster_no_to_monster(monster_id)
        if m != m.base_monster:
            m = m.base_monster
            await ctx.send("I think you meant {} for {}.".format(m.monster_no_na, m.name_na))
        name = str(m.monster_id)

        op = 'EDITED' if name in self.settings.which() else 'ADDED'
        self.settings.addWhich(name, definition)
        await ctx.send("PAD which info successfully {}.".format(op))

    @padglobal.command()
    async def rmwhich(self, ctx, *, monster_id: int):
        """Removes an entry from the which monster evo list."""
        m = monster_no_to_monster(monster_id)
        if m != m.base_monster:
            m = m.base_monster
            await ctx.send("I think you meant {} for {}.".format(m.monster_no_na, m.name_na))
        name = str(m.monster_id)

        if name not in self.settings.which():
            await ctx.send("Which item doesn't exist.")
            return

        self.settings.rmWhich(name)
        await ctx.send("done")

    @padglobal.command()
    @checks.is_owner()
    async def addadmin(self, ctx, user: discord.Member):
        """Adds a user to the pad global admin"""
        self.settings.addAdmin(user.id)
        await ctx.send("done")

    @padglobal.command()
    @checks.is_owner()
    async def rmadmin(self, ctx, user: discord.Member):
        """Removes a user from the pad global admin"""
        self.settings.rmAdmin(user.id)
        await ctx.send("done")

    @padglobal.command()
    @checks.is_owner()
    async def setemojiservers(self, ctx, *, emoji_servers=''):
        """Set the emoji servers by ID (csv)"""
        self.settings.emojiServers().clear()
        if emoji_servers:
            self.settings.setEmojiServers(emoji_servers.split(','))
        await ctx.send(inline('Set {} servers'.format(len(self.settings.emojiServers()))))

    def _get_emojis(self):
        emojis = list()
        for server_id in self.settings.emojiServers():
            emojis.extend(self.bot.get_guild(int(server_id)).emojis)
        return emojis

    @padglobal.command()
    async def addemoji(self, ctx, monster_id: int, server: str = 'jp'):
        """Create padglobal monster emoji by id..

        Uses jp monster IDs by default. You only need to change to na if you want to add
        voltron or something.

        If you add a jp ID, it will look like ':pad_123:'.
        If you add a na ID, it will look like ':pad_na_123:'.
        """
        all_emoji_servers = self.settings.emojiServers()
        if not all_emoji_servers:
            await ctx.send('No emoji servers set')
            return

        if server not in ['na', 'jp']:
            await ctx.send('Server must be one of [jp, na]')
            return

        if monster_id <= 0:
            await ctx.send('Invalid monster id')
            return

        server_ids = self.settings.emojiServers()
        all_emojis = self._get_emojis()

        source_url = PORTRAIT_TEMPLATE.format(server, monster_id)
        emoji_name = 'pad_' + ('na_' if server == 'na' else '') + str(monster_id)

        for e in all_emojis:
            if emoji_name == e.name:
                await ctx.send(inline('Already exists'))
                return

        for server_id in server_ids:
            emoji_server = self.bot.get_guild(int(server_id))
            if len(emoji_server.emojis) < 50:
                break

        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(source_url) as resp:
                    emoji_content = await resp.read()
                    await emoji_server.create_custom_emoji(name=emoji_name, image=emoji_content)
                    await ctx.send(inline('Done creating emoji named {}'.format(emoji_name)))
        except Exception as ex:
            await ctx.send(box('Error:\n' + str(ex)))

    @commands.Cog.listener('on_message')
    async def checkCC(self, message):
        if message.author.id == self.bot.user.id:
            return

        global_ignores = {'blacklist': []}  # self.bot.get_cog('Core').global_ignores
        if message.author.id in global_ignores["blacklist"]:
            return False

        if len(message.content) < 2:
            return

        prefix = await self.get_prefix(message)

        if not prefix:
            return

        cmd = message.content[len(prefix):]
        final_cmd = self._lookup_command(cmd)
        if final_cmd is None:
            return

        if self.settings.checkDisabled(message):
            await message.channel.send(inline(DISABLED_MSG))
            return

        if final_cmd != cmd:
            await message.channel.send(inline('Corrected to: {}'.format(final_cmd)))
        result = self.c_commands[final_cmd]

        cmd = self.format_cc(result, message)

        await message.channel.send(result)

    def _lookup_command(self, cmd):
        """Returns the corrected cmd name.

        Checks the raw command list, and if that fails, applies some corrections and takes
        the most likely result. Returns None if no good match.
        """
        cmdlist = self.c_commands.keys()
        if cmd in cmdlist:
            return cmd
        elif cmd.lower() in cmdlist:
            return cmd.lower()
        else:
            corrected_cmds = self._get_corrected_cmds(cmd, cmdlist)
            if corrected_cmds:
                return corrected_cmds[0]

        return None

    def _get_corrected_cmds(self, cmd, options):
        """Applies some corrections to cmd and returns the best matches in order."""
        cmd = cmd.lower()
        adjusted_cmd = [
            cmd + 's',
            cmd + '?',
            cmd + 's?',
            cmd.rstrip('?'),
            cmd.rstrip('s'),
            cmd.rstrip('s?'),
            cmd.rstrip('s?') + 's',
            cmd.rstrip('s?') + '?',
            cmd.rstrip('s?') + 's?',
        ]
        return [x for x in adjusted_cmd if x in options]

    async def get_prefix(self, message):
        for p in await self.bot.get_prefix(message):
            if message.content.startswith(p):
                return p
        return False

    def format_cc(self, command, message):
        results = re.findall("\{([^}]+)\}", command)
        for result in results:
            param = self.transform_parameter(result, message)
            command = command.replace("{" + result + "}", param)
        return command

    def transform_parameter(self, result, message):
        """
        For security reasons only specific objects are allowed
        Internals are ignored
        """
        raw_result = "{" + result + "}"
        objects = {
            "message": message,
            "author": message.author,
            "channel": message.channel,
            "server": message.guild
        }
        if result in objects:
            return str(objects[result])
        try:
            first, second = result.split(".")
        except ValueError:
            return raw_result
        if first in objects and not second.startswith("_"):
            first = objects[first]
        else:
            return raw_result
        return str(getattr(first, second, raw_result))

    @commands.command(aliases=["guides"])
    async def guide(self, ctx, *, term: str = None):
        """Shows Leader and Dungeon guide entries."""
        if await self._check_disabled(ctx):
            return

        if term is None:
            await self.send_guide(ctx)
            return

        term, text, err = self.get_guide_text(term)
        if text is None:
            await ctx.send(inline(err))
            return

        await ctx.send(text)

    def get_guide_text(self, term: str):
        term = term.lower()
        if term in self.settings.dungeonGuide():
            return term, self.settings.dungeonGuide()[term], None

        nm, _, _ = lookup_named_monster(term)
        if nm is None:
            return None, None, 'No dungeon or monster matched that query'

        name = nm.group_computed_basename.title()
        definition = self.settings.leaderGuide().get(str(nm.base_monster_no), None)
        if definition is None:
            return None, None, 'A monster matched that query but has no guide'

        return name, definition, None

    async def send_guide(self, ctx):
        msg = self.guide_to_text()
        for page in pagify(msg):
            await ctx.author.send(page)

    def guide_to_text(self):
        msg = '__**Dungeon Guides**__'
        dungeon_guide = self.settings.dungeonGuide()
        for term in sorted(dungeon_guide.keys()):
            definition = dungeon_guide[term]
            msg += '\n**{}** :\n{}\n'.format(term, definition)

        leader_guide = self.settings.leaderGuide()
        name_to_guide = {self.term_to_monster_name(
            monster_id): definition for monster_id, definition in leader_guide.items()}

        msg += '\n\n__**Leader Guides**__'
        for term in sorted(name_to_guide.keys()):
            definition = name_to_guide[term]
            msg += '\n**{}** :\n{}\n'.format(term, definition)

        return msg

    @commands.command()
    async def guideto(self, ctx, to_user: discord.Member, *, term: str):
        """Send a user a dungeon/leader guide entry.

        ^guideto @tactical_retreat osc10
        """
        if await self._check_disabled(ctx):
            return

        term, text, err = self.get_guide_text(term)
        if text is None:
            await ctx.send(inline(err))
            return

        result_output = '**Guide for {}**\n{}'.format(term, text)
        result = "{} asked me to send you this:\n{}".format(
            ctx.author.name, result_output)
        await to_user.send_message(result)
        msg = "Sent guide for {} to {}".format(term, to_user.name)
        await ctx.send(inline(msg))

    @padglobal.command()
    async def adddungeonguide(self, ctx, term: str, *, definition: str):
        term = term.lower()
        op = 'EDITED' if term in self.settings.dungeonGuide() else 'ADDED'
        self.settings.addDungeonGuide(term, definition)
        await ctx.send("PAD dungeon guide successfully {}.".format(op))

    @padglobal.command()
    async def rmdungeonguide(self, ctx, term: str):
        term = term.lower()
        if term not in self.settings.dungeonGuide():
            await ctx.send("DungeonGuide doesn't exist.")
            return

        self.settings.rmDungeonGuide(term)
        await ctx.send("done")

    @padglobal.command()
    async def addleaderguide(self, ctx, monster_id: int, *, definition: str):
        m = monster_no_to_monster(monster_id)
        if m != m.base_monster:
            m = m.base_monster
            await ctx.send("I think you meant {} for {}.".format(m.monster_no_na, m.name_na))
        name = str(m.monster_id)

        op = 'EDITED' if name in self.settings.leaderGuide() else 'ADDED'
        self.settings.addLeaderGuide(name, definition)
        await ctx.send("PAD leader guide info successfully {}.".format(op))

    @padglobal.command()
    async def rmleaderguide(self, ctx, monster_id: int):
        m = monster_no_to_monster(monster_id)
        if m != m.base_monster:
            m = m.base_monster
            await ctx.send("I think you meant {} for {}.".format(m.monster_no_na, m.name_na))
        name = str(m.monster_id)

        if name not in self.settings.leaderGuide():
            await ctx.send("LeaderGuide doesn't exist.")
            return

        self.settings.rmLeaderGuide(name)
        await ctx.send("done")

    def term_to_monster_name(self, term):
        nm, _, _ = lookup_named_monster(term)
        return nm.group_computed_basename.title()


def check_simple_tree(monster):
    attr1 = monster.attr1
    active_skill = monster.active_skill
    for m in monster.alt_evos:
        if m.attr1 != attr1 or m.active_skill != active_skill:
            return False
        if m.is_equip:
            return False
        if 'awoken' in m.name_na.lower():
            return False
    return True


class PadGlobalSettings(CogSettings):
    def make_default_settings(self):
        config = {
            'admins': [],
            'faq': [],
            'boards': [],
            'glossary': {},
            'which': {},
            'boss': {},
            'disabled_servers': [],
        }
        return config

    def admins(self):
        return self.bot_settings['admins']

    def checkAdmin(self, user_id):
        admins = self.admins()
        return user_id in admins

    def addAdmin(self, user_id):
        admins = self.admins()
        if user_id not in admins:
            admins.append(user_id)
            self.save_settings()

    def rmAdmin(self, user_id):
        admins = self.admins()
        if user_id in admins:
            admins.remove(user_id)
            self.save_settings()

    def faq(self):
        key = 'faq'
        if key not in self.bot_settings:
            self.bot_settings[key] = []
        return self.bot_settings[key]

    def boards(self):
        key = 'boards'
        if key not in self.bot_settings:
            self.bot_settings[key] = {}
        return self.bot_settings[key]

    def clearCmd(self, cmd):
        if cmd in self.faq():
            self.faq().remove(cmd)
        if cmd in self.boards():
            self.boards().remove(cmd)

    def setGeneral(self, cmd):
        self.clearCmd(cmd)
        self.save_settings()

    def setFaq(self, cmd):
        self.clearCmd(cmd)
        self.faq().append(cmd)
        self.save_settings()

    def setBoards(self, cmd):
        self.clearCmd(cmd)
        self.boards().append(cmd)
        self.save_settings()

    def glossary(self):
        key = 'glossary'
        if key not in self.bot_settings:
            self.bot_settings[key] = {}
        return self.bot_settings[key]

    def addGlossary(self, term, definition):
        self.glossary()[term] = definition
        self.save_settings()

    def rmGlossary(self, term):
        glossary = self.glossary()
        if term in glossary:
            glossary.pop(term)
            self.save_settings()

    def boss(self):
        key = 'boss'
        if key not in self.bot_settings:
            self.bot_settings[key] = {}
        return self.bot_settings[key]

    def addBoss(self, term, definition):
        self.boss()[term] = definition
        self.save_settings()

    def rmBoss(self, term):
        boss = self.boss()
        if term in boss:
            boss.pop(term)
            self.save_settings()

    def which(self):
        key = 'which'
        if key not in self.bot_settings:
            self.bot_settings[key] = {}
        return self.bot_settings[key]

    def addWhich(self, name, text):
        self.which()[name] = text
        self.save_settings()

    def rmWhich(self, name):
        which = self.which()
        if name in which:
            which.pop(name)
            self.save_settings()

    def emojiServers(self):
        key = 'emoji_servers'
        if key not in self.bot_settings:
            self.bot_settings[key] = []
        return self.bot_settings[key]

    def setEmojiServers(self, emoji_servers):
        es = self.emojiServers()
        es.clear()
        es.extend(emoji_servers)
        self.save_settings()

    def leaderGuide(self):
        key = 'leader_guide'
        if key not in self.bot_settings:
            self.bot_settings[key] = {}
        return self.bot_settings[key]

    def addLeaderGuide(self, name, text):
        self.leaderGuide()[name] = text
        self.save_settings()

    def rmLeaderGuide(self, name):
        options = self.leaderGuide()
        if name in options:
            options.pop(name)
            self.save_settings()

    def dungeonGuide(self):
        key = 'dungeon_guide'
        if key not in self.bot_settings:
            self.bot_settings[key] = {}
        return self.bot_settings[key]

    def addDungeonGuide(self, name, text):
        self.dungeonGuide()[name] = text
        self.save_settings()

    def rmDungeonGuide(self, name):
        options = self.dungeonGuide()
        if name in options:
            options.pop(name)
            self.save_settings()

    def disabledServers(self):
        return self.bot_settings['disabled_servers']

    def checkDisabled(self, ctx_or_msg):
        if hasattr(ctx_or_msg, 'message'):
            ctx_or_msg = ctx_or_msg.message
        if ctx_or_msg.guild is None:
            return False
        return ctx_or_msg.guild.id in self.disabledServers()

    def addDisabledServer(self, server_id):
        disabled_servers = self.disabledServers()
        if server_id not in disabled_servers:
            disabled_servers.append(server_id)
            self.save_settings()

    def rmDisabledServer(self, server_id):
        disabled_servers = self.disabledServers()
        if server_id in disabled_servers:
            disabled_servers.remove(server_id)
            self.save_settings()
