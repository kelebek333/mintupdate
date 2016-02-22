#!/usr/bin/python3

import subprocess
import os
import re
import tempfile
import threading
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0') # Needed to get xid
from gi.repository import Gtk, Gdk, GdkX11

KERNEL_INFO_DIR = "/usr/share/mint-kernel-info"

# Using these two as hack to get around the lack of gtk_box_set_center_widget in 3.10
VERSION_GROUP = Gtk.SizeGroup(Gtk.SizeGroupMode.HORIZONTAL)
INFO_GROUP = Gtk.SizeGroup(Gtk.SizeGroupMode.HORIZONTAL)

def list_header_func(row, before, user_data):
    if before and not row.get_header():
        row.set_header(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

class InstallKernelThread(threading.Thread):
    def __init__(self, version, application, window, remove=False):
        threading.Thread.__init__(self)
        self.version = version
        self.window = window
        self.remove = remove
        self.application = application

    def run(self):
        cmd = ["pkexec", "/usr/sbin/synaptic", "--hide-main-window",  \
                "--non-interactive", "--parent-window-id", "%s" % self.window.get_window().get_xid()]
        cmd.append("-o")
        cmd.append("Synaptic::closeZvt=true")
        cmd.append("--progress-str")
        cmd.append("\"" + _("Please wait, this can take some time") + "\"")
        cmd.append("--finish-str")
        if self.remove:
            cmd.append("\"" + _("The %s kernel was removed") % self.version + "\"")
        else:
            cmd.append("\"" + _("The %s kernel was installed") % self.version + "\"")
        f = tempfile.NamedTemporaryFile()

        for pkg in ['linux-headers-%s' % self.version, 'linux-headers-%s-generic' % self.version, 'linux-image-%s-generic' % self.version, 'linux-image-extra-%s-generic' % self.version]:
            if self.remove:
                pkg_line = "%s\tdeinstall\n" % pkg
            else:
                pkg_line = "%s\tinstall\n" % pkg
            f.write(pkg_line.encode("utf-8"))
        cmd.append("--set-selections-file")
        cmd.append("%s" % f.name)
        f.flush()
        comnd = subprocess.Popen(' '.join(cmd), stdout=self.application.logger.log, stderr=self.application.logger.log, shell=True)
        returnCode = comnd.wait()
        f.close()   

class SidebarSwitcherRow(Gtk.ListBoxRow):
    def __init__(self, name, widget):
        Gtk.ListBoxRow.__init__(self)

        self.name = name
        self.add(widget)

class SidebarSwitcher(Gtk.Bin):
    def __init__(self):
        Gtk.Bin.__init__(self)

        self.stack = None
        scw = Gtk.ScrolledWindow()
        scw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scw.set_shadow_type(Gtk.ShadowType.IN)
        self.add(scw)

        self.list_box = Gtk.ListBox()
        self.list_box.set_header_func(list_header_func, None)
        scw.add(self.list_box)
        self.list_box.connect("row-activated", self.on_row_activated)
        Gtk.StyleContext.add_class(Gtk.Widget.get_style_context(self), "sidebar")

    def add_titled(self, name, title):
        label = Gtk.Label(title)
        label.set_margin_top(8)
        label.set_margin_bottom(8)
        row = SidebarSwitcherRow(name, label)
        self.list_box.add(row)

    def on_row_activated(self, widget, row):
        self.stack.set_visible_child_name(row.name)

    def set_stack(self, stack):
        self.stack = stack

class KernelRow(Gtk.ListBoxRow):
    def __init__(self, version, text, installed, used, recommended, installable, has_fixes, has_regressions, window, application):
        Gtk.ListBoxRow.__init__(self)

        self.application = application

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)
        hbox.set_margin_left(20)
        hbox.set_margin_right(20)
        vbox.pack_start(hbox, True, True, 0)
        version_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox.pack_start(version_box, False, False, 0)
        version_label = Gtk.Label()
        version_label.set_markup("%s" % text)
        version_box.pack_start(version_label, False, False, 0)
        VERSION_GROUP.add_widget(version_box)
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        info_box.set_spacing(6)
        hbox.pack_end(info_box, False, False, 0)
        INFO_GROUP.add_widget(info_box) 

        if installed:
            label = Gtk.Label()
            label.set_margin_right(6)
            label.set_margin_left(6)
            label.props.xalign = 0.5
            label.set_markup("<i>%s</i>" % _("Installed"))
            Gtk.StyleContext.add_class(Gtk.Widget.get_style_context(label), "dim-label")
            hbox.pack_start(label, True, False, 0)
        elif recommended:
            label = Gtk.Label()
            label.set_margin_right(6)
            label.set_margin_left(6)
            label.props.xalign = 0.5
            label.set_markup("<i>%s</i>" % _("Recommended"))
            Gtk.StyleContext.add_class(Gtk.Widget.get_style_context(label), "dim-label")
            hbox.pack_start(label, True, False, 0)

        self.revealer = Gtk.Revealer()
        self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.revealer.set_transition_duration(150)
        vbox.pack_start(self.revealer, True, True, 0)
        hidden_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hidden_box.set_margin_right(20)
        hidden_box.set_margin_left(20)
        hidden_box.set_margin_bottom(6)
        self.revealer.add(hidden_box)

        if has_fixes or has_regressions:
            if has_fixes:
                image = Gtk.Image.new_from_icon_name('emblem-default-symbolic', Gtk.IconSize.MENU)
                image.set_sensitive(False)
                image.set_tooltip_text(_("Has known fixes"))
                info_box.pack_start(image, False, False, 0)
                fixes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                fixes_box.set_margin_bottom(6)
                fixes_header = Gtk.Label()
                fixes_header.set_markup("<b>%s</b>" % _("Fixes"))
                fixes_box.pack_start(fixes_header, True, True, 0)
                hidden_box.pack_start(fixes_box, True, True, 0)

            if has_regressions:
                image = Gtk.Image.new_from_icon_name('edit-delete-symbolic', Gtk.IconSize.MENU)
                image.set_sensitive(False)
                image.set_tooltip_text(_("Has known regressions"))
                info_box.pack_start(image, False, False, 0)
                regressions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                regressions_box.set_margin_bottom(6)
                regressions_header = Gtk.Label()
                regressions_header.set_markup("<b>%s</b>" % _("Known issues"))
                regressions_box.pack_start(regressions_header, True, True, 0)
                hidden_box.pack_start(regressions_box, True, True, 0)

            if os.path.exists(os.path.join(KERNEL_INFO_DIR, version)):
                kernel_file = open(os.path.join(KERNEL_INFO_DIR, version))
                lines = kernel_file.readlines()
                for line in lines:
                    elements = line.split("---")
                    if len(elements) == 4:
                        (prefix, title, url, description) = elements
                        link = Gtk.Label()
                        link.set_markup("<a href='%s'>%s</a>" % (url.strip(), title.strip()))
                        link.set_line_wrap(True)
                        description_label = Gtk.Label()
                        description = description.strip()
                        description = re.sub(r'CVE-(\d+)-(\d+)', r'<a href="http://cve.mitre.org/cgi-bin/cvename.cgi?name=\g<0>">\g<0></a>', description)
                        description_label.set_markup("%s" % description.strip())
                        description_label.set_line_wrap(True)
                        if prefix == "fix":
                            fixes_box.pack_start(link, True, True, 0)
                            fixes_box.pack_start(description_label, True, True, 0)
                        elif prefix == "bug":
                            regressions_box.pack_start(link, True, True, 0)
                            regressions_box.pack_start(description_label, True, True, 0)
        else:
            no_info_label = Gtk.Label()
            no_info_label.set_markup("<b>%s</b>" % _("No information available"))
            no_info_label.set_margin_bottom(6)
            hidden_box.pack_start(no_info_label, True, True, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        button = Gtk.Button.new_with_label("")
        Gtk.StyleContext.add_class(Gtk.Widget.get_style_context(button), "text-button")
        button.set_sensitive(False)
        button.set_tooltip_text("")
        if installed:
            button.set_label(_("Remove"))
            button.connect("clicked", self.install_kernel, version, installed, window)
            if used:
                button.set_tooltip_text(_("This kernel cannot be removed because it is currently in use."))
            else:
                button.set_sensitive(True)
        else:
            button.set_label(_("Install"))
            button.connect("clicked", self.install_kernel, version, installed, window)
            if not installable:
                button.set_tooltip_text(_("This kernel is not installable."))
            else:
                button.set_sensitive(True)
        button_box.pack_end(button, False, False, 0)
        hidden_box.pack_start(button_box, False, False, 0)

    def show_hide_children(self, widget):
        if self.revealer.get_child_revealed():
            self.revealer.set_reveal_child(False)
        else:
            self.revealer.set_reveal_child(True)

    def install_kernel(self, widget, version, installed, window):
        if installed:
            message = _("Are you sure you want to remove the %s kernel?") % version
        else:
            message = _("Are you sure you want to install the %s kernel?") % version
        d = Gtk.MessageDialog(window, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.INFO, Gtk.ButtonsType.YES_NO, message)
        d.set_default_response(Gtk.ResponseType.NO)
        r = d.run()
        d.hide()
        d.destroy()
        if r == Gtk.ResponseType.YES:
            thread = InstallKernelThread(version, self.application, window, installed)
            thread.start()
            window.hide()

class KernelWindow():
    def __init__(self, application):
        self.application = application
        gladefile = "/usr/share/linuxmint/mintupdate/kernels.ui"
        builder = Gtk.Builder()
        builder.add_from_file(gladefile)
        self.window = builder.get_object("window1")
        self.window.set_title("Kernels")
        listbox_series = builder.get_object("listbox_series")
        scrolled_series = builder.get_object("box7")
        kernel_stack_box = builder.get_object("box1")
        main_box = builder.get_object("main_vbox")
        info_box = builder.get_object("intro_box")
        current_label = builder.get_object("label6")

        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.window.add(self.main_stack)

        # Setup the kernel warning page
        self.main_stack.add_named(info_box, "info_box")
        builder.get_object("button_continue").connect("clicked", self.on_continue_clicked, main_box)
        hide_info_checkbox = builder.get_object("checkbutton1").connect("toggled", self.on_info_checkbox_toggled)

        builder.get_object("title_warning").set_markup("<span font_weight='bold' size='x-large'>%s</span>" % _("Warning!"))
        builder.get_object("sub_title_warning").set_markup("<big><b>%s</b></big>" % _("Proceed with caution"))
        builder.get_object("label_warning").set_markup(_("The Linux kernel is a critical part of the system. Regressions can lead to lack of networking, lack of sound, lack of graphical environment or even the inability to boot the computer. Only install or remove kernels if you're experienced with kernels, drivers, dkms and you know how to recover a non-booting computer."))
        builder.get_object("label_more_info_1").set_markup("%s" % _("Fixes can represent bug fixes, improvements in hardware support or security fixes."))
        builder.get_object("label_more_info_2").set_markup("%s" % _("Security fixes are important when local users represent a potential threat (in companies, libraries, schools or public places for instance) or when the computer can be threatened by remote attacks (servers for instance)."))
        builder.get_object("label_more_info_3").set_markup("%s" % _("Bug fixes and hardware improvements are important if one of your devices isn't working as expected and the newer kernel addresses that problem."))
        builder.get_object("label_more_info_4").set_markup("%s" % _("Regressions represent something which worked well and no longer works after an update. It is common in software development that a code change or even a bug fix introduces side effects and breaks something else. Because of regressions it is recommended to be selective when installing updates or newer kernels."))

        # Setup the main kernel page
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_UP_DOWN)

        stack_switcher = SidebarSwitcher()
        stack_switcher.set_stack(stack)
        scrolled_series.pack_start(stack_switcher, True, True, 0)
        kernel_stack_box.pack_start(stack, True, True, 0)

        builder.get_object("button_close").connect("clicked", self.hide_window)

        kernels = subprocess.check_output("/usr/lib/linuxmint/mintUpdate/checkKernels.py | grep \"###\"", shell = True).decode("utf-8")
        kernels = kernels.split("\n")
        kernel_list = []
        pages_needed = []
        for kernel in kernels:
            values = kernel.split('###')
            if len(values) == 7:
                status = values[0]
                if status != "KERNEL":
                    continue
                (status, version, pkg_version, installed, used, recommended, installable) = values
                installed = (installed == "1")
                used = (used == "1")
                recommended = (recommended == "1")
                installable = (installable == "1")
                label = version

                has_fixes = False
                has_regressions = False
                if os.path.exists(os.path.join(KERNEL_INFO_DIR, version)):
                    kernel_file = open(os.path.join(KERNEL_INFO_DIR, version))
                    lines = kernel_file.readlines()
                    num_fixes = 0
                    num_bugs = 0
                    for line in lines:
                        elements = line.split("---")
                        if len(elements) == 4:
                            (prefix, title, url, description) = elements
                            if prefix == "fix":
                                num_fixes += 1
                            elif prefix == "bug":
                                num_bugs += 1
                    if num_fixes > 0:
                        has_fixes = True
                    if num_bugs > 0:
                        has_regressions = True

                if os.path.exists(os.path.join(KERNEL_INFO_DIR, "versions")):
                    kernel_file = open(os.path.join(KERNEL_INFO_DIR, "versions"))
                    lines = kernel_file.readlines()
                    for line in lines:
                        elements = line.split("\t")
                        if len(elements) == 3:
                            (versions_version, versions_tag, versions_upstream) = elements
                            if version in versions_version:
                                label = "%s (%s)" % (version, versions_upstream.strip())

                page_label = label.split(".")[0] + "." + label.split(".")[1]
                kernel_list.append([version, page_label, label, installed, used, recommended, installable, has_fixes, has_regressions])
                if page_label not in pages_needed:
                    pages_needed.append(page_label)

        for page in pages_needed:
            scw = Gtk.ScrolledWindow()
            scw.set_shadow_type(Gtk.ShadowType.IN)
            list_box = Gtk.ListBox()
            list_box.set_header_func(list_header_func, None)
            list_box.set_selection_mode(Gtk.SelectionMode.NONE)
            list_box.set_activate_on_single_click(True)
            scw.add(list_box)
            stack.add_titled(scw, page, page)
            stack_switcher.add_titled(page, page)

            for kernel in kernel_list:
                if kernel[4]:
                    current_label.set_markup("<b>%s %s %s</b>" % (_("Kernel"), kernel[2], _("currently loaded")))
                if kernel[1] == page:
                    row = KernelRow(kernel[0], kernel[2], kernel[3], kernel[4], kernel[5], kernel[6], kernel[7], kernel[8], self.window, self.application)
                    list_box.add(row)

            list_box.connect("row_activated", self.on_row_activated)

        stack_switcher.list_box.select_row(stack_switcher.list_box.get_row_at_index(0))

        self.main_stack.add_named(main_box, "main_box")

        if self.application.settings.get_boolean("hide-kernel-update-warning"):
            self.main_stack.set_visible_child(main_box)
        else:
            self.main_stack.set_visible_child(info_box)

        self.window.show_all()

    def hide_window(self, widget):
        self.window.hide()

    def on_continue_clicked(self, widget, main_box):
        self.main_stack.set_visible_child(main_box)

    def on_info_checkbox_toggled(self, widget):
        self.application.settings.set_boolean("hide-kernel-update-warning", widget.get_active())

    def on_row_activated(self, list_box, row):
        row.show_hide_children(row)
