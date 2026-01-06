#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# A simple wxWidgets UI for audiblez
# Modified for MLX support on Apple Silicon

import numpy as np
import soundfile
import threading
import platform
import subprocess
import io
import os
import wx
from wx.lib.newevent import NewEvent
from wx.lib.scrolledpanel import ScrolledPanel
from PIL import Image
from tempfile import NamedTemporaryFile
from pathlib import Path

from audiblez.voices import voices, flags

# Detect Apple Silicon and use MLX for acceleration
USE_MLX = platform.system() == "Darwin" and platform.machine() == "arm64"

if USE_MLX:
    try:
        from mlx_audio.tts.models.kokoro import KokoroPipeline
        from mlx_audio.tts.utils import load_model

        print("🚀 GUI: Using MLX acceleration for Apple Silicon")
    except ImportError:
        print("⚠️  mlx-audio not installed, falling back to PyTorch")
        USE_MLX = False
        import torch.cuda
        from kokoro import KPipeline
else:
    import torch.cuda
    from kokoro import KPipeline

EVENTS = {
    "CORE_STARTED": NewEvent(),
    "CORE_PROGRESS": NewEvent(),
    "CORE_CHAPTER_STARTED": NewEvent(),
    "CORE_CHAPTER_FINISHED": NewEvent(),
    "CORE_FINISHED": NewEvent(),
}

border = 5


class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        screen_width, screen_h = wx.GetDisplaySize()
        self.window_width = screen_width
        super().__init__(parent, title=title, size=(screen_width, screen_h))

        # Ensure window has minimum size so UI elements are always visible
        self.SetMinSize((900, 700))

        # Maximize the window by default
        self.Maximize(True)

        self.chapters_panel = None
        self.preview_threads = []
        self.selected_chapter = None
        self.selected_book = None
        self.synthesis_in_progress = False

        self.Bind(EVENTS["CORE_STARTED"][1], self.on_core_started)
        self.Bind(EVENTS["CORE_CHAPTER_STARTED"][1], self.on_core_chapter_started)
        self.Bind(EVENTS["CORE_CHAPTER_FINISHED"][1], self.on_core_chapter_finished)
        self.Bind(EVENTS["CORE_PROGRESS"][1], self.on_core_progress)
        self.Bind(EVENTS["CORE_FINISHED"][1], self.on_core_finished)

        self.create_menu()
        self.create_layout()
        self.Show(True)
        if Path("../epub/lewis.epub").exists():
            self.open_epub("../epub/lewis.epub")

    def create_menu(self):
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        open_item = wx.MenuItem(file_menu, wx.ID_OPEN, "&Open\tCtrl+O")
        file_menu.Append(open_item)
        self.Bind(wx.EVT_MENU, self.on_open, open_item)  # Bind the event

        exit_item = wx.MenuItem(file_menu, wx.ID_EXIT, "&Exit\tCtrl+Q")
        file_menu.Append(exit_item)
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)

        menubar.Append(file_menu, "&File")
        self.SetMenuBar(menubar)

    def on_core_started(self, event):
        print("CORE_STARTED")
        self.progress_bar_label.Show()
        self.progress_bar.Show()
        self.progress_bar.SetValue(0)
        self.progress_bar.Layout()
        self.eta_label.Show()
        self.params_panel.Layout()
        self.synth_panel.Layout()

    def on_core_chapter_started(self, event):
        # print('CORE_CHAPTER_STARTED', event.chapter_index)
        self.set_table_chapter_status(event.chapter_index, "⏳ In Progress")

    def on_core_chapter_finished(self, event):
        # print('CORE_CHAPTER_FINISHED', event.chapter_index)
        self.set_table_chapter_status(event.chapter_index, "✅ Done")
        self.start_button.Show()

    def on_core_progress(self, event):
        # print('CORE_PROGRESS', event.progress)
        self.progress_bar.SetValue(event.stats.progress)
        self.progress_bar_label.SetLabel(f"Synthesis Progress: {event.stats.progress}%")
        self.eta_label.SetLabel(f"Estimated Time Remaining: {event.stats.eta}")
        self.synth_panel.Layout()

    def on_core_finished(self, event):
        self.synthesis_in_progress = False
        self.open_folder_with_explorer(self.output_folder_text_ctrl.GetValue())
        self.new_book_button.Show()
        self.synth_panel.Layout()

    def create_layout(self):
        # Panels layout looks like this:
        # splitter
        #     splitter_left
        #         chapters_panel
        #     splitter_right
        #         center_panel
        #             text_area
        #         right_panel
        #             book_info_panel_box
        #                 book_info_panel
        #                     cover_bitmap
        #                     book_details_panel
        #             param_panel_box
        #                  param_panel
        #                      ...
        #             synth_panel_box
        #                  synth_panel
        #                      start_button
        #                      ...

        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.main_sizer)

        # Create welcome panel (shown before EPUB is loaded)
        self.welcome_panel = wx.Panel(self)
        welcome_sizer = wx.BoxSizer(wx.VERTICAL)
        self.welcome_panel.SetSizer(welcome_sizer)

        # Add vertical spacer to center content
        welcome_sizer.AddStretchSpacer(1)

        # App title
        title_font = wx.Font(
            32, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD
        )
        title_label = wx.StaticText(self.welcome_panel, label="🎧 Audiblez")
        title_label.SetFont(title_font)
        welcome_sizer.Add(title_label, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Subtitle
        subtitle_font = wx.Font(
            16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL
        )
        subtitle_label = wx.StaticText(
            self.welcome_panel, label="Generate Audiobooks from E-books"
        )
        subtitle_label.SetFont(subtitle_font)
        welcome_sizer.Add(subtitle_label, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        # Description
        desc_label = wx.StaticText(
            self.welcome_panel,
            label="Convert your EPUB files to high-quality audiobooks using Kokoro TTS",
        )
        welcome_sizer.Add(desc_label, 0, wx.ALIGN_CENTER | wx.ALL, 20)

        # Buttons panel (centered)
        buttons_panel = wx.Panel(self.welcome_panel)
        buttons_sizer = wx.BoxSizer(wx.HORIZONTAL)
        buttons_panel.SetSizer(buttons_sizer)

        # Open EPUB button (larger)
        open_epub_button = wx.Button(
            buttons_panel, label="📁 Open EPUB", size=(150, 40)
        )
        open_epub_button.Bind(wx.EVT_BUTTON, self.on_open)
        buttons_sizer.Add(open_epub_button, 0, wx.ALL, 10)

        # About button
        help_button = wx.Button(buttons_panel, label="ℹ️ About", size=(100, 40))
        help_button.Bind(wx.EVT_BUTTON, lambda event: self.about_dialog())
        buttons_sizer.Add(help_button, 0, wx.ALL, 10)

        welcome_sizer.Add(buttons_panel, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        # Add vertical spacer to center content
        welcome_sizer.AddStretchSpacer(1)

        # Splitter panel (shown after EPUB is loaded)
        self.splitter = wx.Panel(self)
        self.splitter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.splitter.SetSizer(self.splitter_sizer)
        self.splitter.Hide()  # Hidden initially

        self.main_sizer.Add(self.welcome_panel, 1, wx.EXPAND)
        self.main_sizer.Add(self.splitter, 1, wx.EXPAND)

    def create_layout_for_ebook(self, splitter):
        splitter_left = wx.Panel(splitter, -1)
        splitter_right = wx.Panel(self.splitter)
        self.splitter_left, self.splitter_right = splitter_left, splitter_right

        # Set minimum sizes to ensure panels are visible on launch
        splitter_left.SetMinSize((250, 400))
        splitter_right.SetMinSize((500, 400))

        self.splitter_sizer.Add(splitter_left, 1, wx.ALL | wx.EXPAND, 5)
        self.splitter_sizer.Add(splitter_right, 2, wx.ALL | wx.EXPAND, 5)

        self.left_sizer = wx.BoxSizer(wx.VERTICAL)
        splitter_left.SetSizer(self.left_sizer)

        # add center panel with large text area
        self.center_panel = wx.Panel(splitter_right)
        self.center_sizer = wx.BoxSizer(wx.VERTICAL)
        self.center_panel.SetSizer(self.center_sizer)
        self.text_area = wx.TextCtrl(
            self.center_panel,
            style=wx.TE_MULTILINE,
            size=(int(self.window_width * 0.4), -1),
        )
        font = wx.Font(14, wx.MODERN, wx.NORMAL, wx.NORMAL)
        self.text_area.SetFont(font)
        # On text change, update the extracted_text attribute of the selected_chapter:
        self.text_area.Bind(
            wx.EVT_TEXT,
            lambda event: setattr(
                self.selected_chapter, "extracted_text", self.text_area.GetValue()
            ),
        )

        self.chapter_label = wx.StaticText(
            self.center_panel,
            label=f'Edit / Preview content for section "{self.selected_chapter.short_name}":',
        )
        preview_button = wx.Button(self.center_panel, label="🔊 Preview")
        preview_button.Bind(wx.EVT_BUTTON, self.on_preview_chapter)

        self.center_sizer.Add(self.chapter_label, 0, wx.ALL, 5)
        self.center_sizer.Add(preview_button, 0, wx.ALL, 5)
        self.center_sizer.Add(self.text_area, 1, wx.ALL | wx.EXPAND, 5)

        splitter_right_sizer = wx.BoxSizer(wx.HORIZONTAL)
        splitter_right.SetSizer(splitter_right_sizer)

        self.create_right_panel(splitter_right)

        # Set minimum sizes for center and right panels
        self.center_panel.SetMinSize((250, 300))
        self.right_panel.SetMinSize((450, 300))

        splitter_right_sizer.Add(self.center_panel, 1, wx.ALL | wx.EXPAND, 5)
        splitter_right_sizer.Add(self.right_panel, 1, wx.ALL | wx.EXPAND, 5)

    def about_dialog(self):
        msg = (
            "A simple tool to generate audiobooks from EPUB files using Kokoro-82M models\n"
            + "Distributed under the MIT License.\n\n"
            + "by Claudio Santini 2025\nand many contributors.\n\n"
            + "https://claudio.uk\n\n"
        )
        wx.MessageBox(msg, "Audiblez")

    def create_right_panel(self, splitter_right):
        self.right_panel = wx.Panel(splitter_right)
        self.right_sizer = wx.BoxSizer(wx.VERTICAL)
        self.right_panel.SetSizer(self.right_sizer)

        self.book_info_panel_box = wx.Panel(self.right_panel, style=wx.SUNKEN_BORDER)
        book_info_panel_box_sizer = wx.StaticBoxSizer(
            wx.VERTICAL, self.book_info_panel_box, "Book Details"
        )
        self.book_info_panel_box.SetSizer(book_info_panel_box_sizer)
        self.right_sizer.Add(self.book_info_panel_box, 1, wx.ALL | wx.EXPAND, 5)

        self.book_info_panel = wx.Panel(self.book_info_panel_box, style=wx.BORDER_NONE)
        self.book_info_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.book_info_panel.SetSizer(self.book_info_sizer)
        book_info_panel_box_sizer.Add(self.book_info_panel, 1, wx.ALL | wx.EXPAND, 5)

        # Add cover image
        self.cover_bitmap = wx.StaticBitmap(self.book_info_panel, -1)
        self.book_info_sizer.Add(self.cover_bitmap, 0, wx.ALL, 5)

        self.cover_bitmap.Refresh()
        self.book_info_panel.Refresh()
        self.book_info_panel.Layout()
        self.cover_bitmap.Layout()

        self.create_book_details_panel()
        self.create_params_panel()
        self.create_synthesis_panel()

    def create_book_details_panel(self):
        book_details_panel = wx.Panel(self.book_info_panel)
        book_details_sizer = wx.GridBagSizer(10, 10)
        book_details_panel.SetSizer(book_details_sizer)
        self.book_info_sizer.Add(book_details_panel, 1, wx.ALL | wx.EXPAND, 5)

        # Add title with wrapping
        title_label = wx.StaticText(book_details_panel, label="Title:")
        title_text = wx.StaticText(book_details_panel, label=self.selected_book_title)
        title_text.Wrap(200)  # Enable text wrapping
        book_details_sizer.Add(title_label, pos=(0, 0), flag=wx.ALL, border=5)
        book_details_sizer.Add(
            title_text, pos=(0, 1), flag=wx.ALL | wx.EXPAND, border=5
        )

        # Add Author with wrapping
        author_label = wx.StaticText(book_details_panel, label="Author:")
        author_text = wx.StaticText(book_details_panel, label=self.selected_book_author)
        author_text.Wrap(200)  # Enable text wrapping
        book_details_sizer.Add(author_label, pos=(1, 0), flag=wx.ALL, border=5)
        book_details_sizer.Add(
            author_text, pos=(1, 1), flag=wx.ALL | wx.EXPAND, border=5
        )

        # Add Total length
        length_label = wx.StaticText(book_details_panel, label="Total Length:")
        if not hasattr(self, "document_chapters"):
            total_len = 0
        else:
            total_len = sum([len(c.extracted_text) for c in self.document_chapters])
        length_text = wx.StaticText(
            book_details_panel, label=f"{total_len:,} characters"
        )
        book_details_sizer.Add(length_label, pos=(2, 0), flag=wx.ALL, border=5)
        book_details_sizer.Add(
            length_text, pos=(2, 1), flag=wx.ALL | wx.EXPAND, border=5
        )

        # Make column 1 growable so text doesn't get cut off (must be after items are added)
        book_details_sizer.AddGrowableCol(1, 1)

    def create_params_panel(self):
        panel_box = wx.Panel(self.right_panel, style=wx.SUNKEN_BORDER)
        panel_box_sizer = wx.StaticBoxSizer(
            wx.VERTICAL, panel_box, "Audiobook Parameters"
        )
        panel_box.SetSizer(panel_box_sizer)

        panel = self.params_panel = wx.Panel(panel_box)
        panel_box_sizer.Add(panel, 1, wx.ALL | wx.EXPAND, 5)
        self.right_sizer.Add(panel_box, 1, wx.ALL | wx.EXPAND, 5)
        sizer = wx.GridBagSizer(10, 10)
        panel.SetSizer(sizer)

        row = 0

        # TTS Model selection (Kokoro vs Chatterbox)
        tts_model_label = wx.StaticText(panel, label="TTS Model:")
        tts_models = ["Kokoro (Multilingual)", "Chatterbox Turbo (English)"]
        self.selected_tts_model = "kokoro"
        self.tts_model_dropdown = wx.ComboBox(
            panel, choices=tts_models, value=tts_models[0], style=wx.CB_READONLY
        )
        self.tts_model_dropdown.Bind(wx.EVT_COMBOBOX, self.on_select_tts_model)
        sizer.Add(tts_model_label, pos=(row, 0), flag=wx.ALL, border=border)
        sizer.Add(
            self.tts_model_dropdown,
            pos=(row, 1),
            flag=wx.ALL | wx.EXPAND,
            border=border,
        )
        row += 1

        # Hardware Engine selection (CPU/MLX/CUDA)
        engine_label = wx.StaticText(panel, label="Hardware:")
        engine_radio_panel = wx.Panel(panel)
        cpu_radio = wx.RadioButton(engine_radio_panel, label="CPU", style=wx.RB_GROUP)

        if USE_MLX:
            mlx_radio = wx.RadioButton(engine_radio_panel, label="MLX (Apple Silicon)")
            mlx_radio.SetValue(True)
            sizer.Add(engine_label, pos=(row, 0), flag=wx.ALL, border=border)
            sizer.Add(
                engine_radio_panel, pos=(row, 1), flag=wx.ALL | wx.EXPAND, border=border
            )
            engine_radio_panel_sizer = wx.BoxSizer(wx.HORIZONTAL)
            engine_radio_panel.SetSizer(engine_radio_panel_sizer)
            engine_radio_panel_sizer.Add(mlx_radio, 0, wx.ALL, 5)
            engine_radio_panel_sizer.Add(cpu_radio, 0, wx.ALL, 5)
        else:
            cuda_radio = wx.RadioButton(engine_radio_panel, label="CUDA")
            if torch.cuda.is_available():
                cuda_radio.SetValue(True)
            else:
                cpu_radio.SetValue(True)
            sizer.Add(engine_label, pos=(row, 0), flag=wx.ALL, border=border)
            sizer.Add(
                engine_radio_panel, pos=(row, 1), flag=wx.ALL | wx.EXPAND, border=border
            )
            engine_radio_panel_sizer = wx.BoxSizer(wx.HORIZONTAL)
            engine_radio_panel.SetSizer(engine_radio_panel_sizer)
            engine_radio_panel_sizer.Add(cpu_radio, 0, wx.ALL, 5)
            engine_radio_panel_sizer.Add(cuda_radio, 0, wx.ALL, 5)
            cpu_radio.Bind(
                wx.EVT_RADIOBUTTON, lambda event: torch.set_default_device("cpu")
            )
            cuda_radio.Bind(
                wx.EVT_RADIOBUTTON, lambda event: torch.set_default_device("cuda")
            )
        row += 1

        # Voice selection (for Kokoro)
        flag_and_voice_list = []
        for code, l in voices.items():
            for v in l:
                flag_and_voice_list.append(f"{flags[code]} {v}")

        self.voice_label = wx.StaticText(panel, label="Voice:")
        default_voice = flag_and_voice_list[0]
        self.selected_voice = default_voice
        self.voice_dropdown = wx.ComboBox(
            panel, choices=flag_and_voice_list, value=default_voice
        )
        self.voice_dropdown.Bind(wx.EVT_COMBOBOX, self.on_select_voice)
        sizer.Add(self.voice_label, pos=(row, 0), flag=wx.ALL, border=border)
        sizer.Add(
            self.voice_dropdown, pos=(row, 1), flag=wx.ALL | wx.EXPAND, border=border
        )
        self.voice_row = row
        row += 1

        # Voice Cloning section (for Chatterbox)
        self.ref_audio_label = wx.StaticText(panel, label="Clone Voice:")
        self.ref_audio_path = None

        # Create a sub-panel for the ref audio controls
        ref_audio_panel = wx.Panel(panel)
        ref_audio_sizer = wx.BoxSizer(wx.HORIZONTAL)
        ref_audio_panel.SetSizer(ref_audio_sizer)

        # Create controls with ref_audio_panel as parent (not panel)
        self.ref_audio_text_ctrl = wx.TextCtrl(
            ref_audio_panel, value="(Optional) Select audio file..."
        )
        self.ref_audio_text_ctrl.SetEditable(False)
        self.ref_audio_button = wx.Button(ref_audio_panel, label="📂")
        self.ref_audio_button.Bind(wx.EVT_BUTTON, self.on_select_ref_audio)

        ref_audio_sizer.Add(self.ref_audio_text_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)
        ref_audio_sizer.Add(self.ref_audio_button, 0)

        sizer.Add(self.ref_audio_label, pos=(row, 0), flag=wx.ALL, border=border)
        sizer.Add(ref_audio_panel, pos=(row, 1), flag=wx.ALL | wx.EXPAND, border=border)
        self.ref_audio_panel = ref_audio_panel
        self.clone_voice_row = row
        # Initially hide voice cloning (shown when Chatterbox selected)
        self.ref_audio_label.Hide()
        self.ref_audio_panel.Hide()
        row += 1

        # Speed
        speed_label = wx.StaticText(panel, label="Speed:")
        speed_text_input = wx.TextCtrl(panel, value="1.0")
        self.selected_speed = "1.0"
        speed_text_input.Bind(wx.EVT_TEXT, self.on_select_speed)
        sizer.Add(speed_label, pos=(row, 0), flag=wx.ALL, border=border)
        sizer.Add(
            speed_text_input, pos=(row, 1), flag=wx.ALL | wx.EXPAND, border=border
        )
        row += 1

        # Output folder
        output_folder_label = wx.StaticText(panel, label="Output Folder:")
        default_path = str(Path.home() / "Downloads")
        self.output_folder_text_ctrl = wx.TextCtrl(panel, value=default_path)
        self.output_folder_text_ctrl.SetEditable(False)
        output_folder_button = wx.Button(panel, label="📂 Select")
        output_folder_button.Bind(wx.EVT_BUTTON, self.open_output_folder_dialog)
        sizer.Add(output_folder_label, pos=(row, 0), flag=wx.ALL, border=border)
        sizer.Add(
            self.output_folder_text_ctrl,
            pos=(row, 1),
            flag=wx.ALL | wx.EXPAND,
            border=border,
        )
        row += 1
        sizer.Add(output_folder_button, pos=(row, 1), flag=wx.ALL, border=border)

        # Make column 1 growable so controls expand properly
        sizer.AddGrowableCol(1, 1)

    def create_synthesis_panel(self):
        # Think and identify layout issue with the folling code
        panel_box = wx.Panel(self.right_panel, style=wx.SUNKEN_BORDER)
        panel_box_sizer = wx.StaticBoxSizer(
            wx.VERTICAL, panel_box, "Audiobook Generation Status"
        )
        panel_box.SetSizer(panel_box_sizer)

        panel = self.synth_panel = wx.Panel(panel_box)
        panel_box_sizer.Add(panel, 1, wx.ALL | wx.EXPAND, 5)
        self.right_sizer.Add(panel_box, 1, wx.ALL | wx.EXPAND, 5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Add Start button
        self.start_button = wx.Button(panel, label="🚀 Start Audiobook Synthesis")
        self.start_button.Bind(wx.EVT_BUTTON, self.on_start)
        sizer.Add(self.start_button, 0, wx.ALL, 5)

        # Add Choose Another Book button (visible before synthesis)
        self.choose_book_button = wx.Button(panel, label="📚 Choose Another Book")
        self.choose_book_button.Bind(wx.EVT_BUTTON, self.on_choose_another_book)
        sizer.Add(self.choose_book_button, 0, wx.ALL, 5)

        # Add Stop button
        # self.stop_button = wx.Button(panel, label="⏹️ Stop Synthesis")
        # self.stop_button.Bind(wx.EVT_BUTTON, self.on_stop)
        # sizer.Add(self.stop_button, 0, wx.ALL, 5)
        # self.stop_button.Hide()

        # Add Progress Bar label:
        self.progress_bar_label = wx.StaticText(panel, label="Synthesis Progress:")
        sizer.Add(self.progress_bar_label, 0, wx.ALL, 5)
        self.progress_bar = wx.Gauge(panel, range=100, style=wx.GA_PROGRESS)
        self.progress_bar.SetMinSize((-1, 30))
        sizer.Add(self.progress_bar, 0, wx.ALL | wx.EXPAND, 5)
        self.progress_bar_label.Hide()
        self.progress_bar.Hide()

        # Add Start New Book button (Hidden initially)
        self.new_book_button = wx.Button(panel, label="✨ Start Another Book")
        self.new_book_button.Bind(wx.EVT_BUTTON, self.on_new_book)
        self.new_book_button.Hide()
        sizer.Add(self.new_book_button, 0, wx.ALL, 5)

        # Add ETA Label
        self.eta_label = wx.StaticText(panel, label="Estimated Time Remaining: ")
        self.eta_label.Hide()
        sizer.Add(self.eta_label, 0, wx.ALL, 5)

    def on_new_book(self, event):
        self.new_book_button.Hide()
        self.progress_bar.Hide()
        self.progress_bar_label.Hide()
        self.eta_label.Hide()
        self.start_button.Enable()
        self.params_panel.Enable()

        # Reset table checkboxes
        self.table.EnableCheckBoxes(True)

        # Go back to start screen
        self.splitter.Hide()
        self.welcome_panel.Show()
        self.Layout()

    def on_choose_another_book(self, event):
        """Allow user to choose a different book without going back to welcome screen."""
        with wx.FileDialog(
            self,
            "Open EPUB File",
            wildcard="*.epub",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            file_path = dialog.GetPath()
            if file_path:
                print(f"Switching to: {file_path}")
                wx.CallAfter(self.open_epub, file_path)

    def open_output_folder_dialog(self, event):
        with wx.DirDialog(
            self, "Choose a directory:", style=wx.DD_DEFAULT_STYLE
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            output_folder = dialog.GetPath()
            print(f"Selected output folder: {output_folder}")
            self.output_folder_text_ctrl.SetValue(output_folder)

    def on_select_voice(self, event):
        self.selected_voice = event.GetString()

    def on_select_speed(self, event):
        speed = float(event.GetString())
        print("Selected speed", speed)
        self.selected_speed = speed

    def on_select_tts_model(self, event):
        """Handle TTS model selection change."""
        selection = event.GetString()
        if "Chatterbox" in selection:
            self.selected_tts_model = "chatterbox"
            # Hide voice selection (Chatterbox uses default voice or cloning)
            self.voice_label.Hide()
            self.voice_dropdown.Hide()
            # Show voice cloning option
            self.ref_audio_label.Show()
            self.ref_audio_panel.Show()
        else:
            self.selected_tts_model = "kokoro"
            # Show voice selection for Kokoro
            self.voice_label.Show()
            self.voice_dropdown.Show()
            # Hide voice cloning option
            self.ref_audio_label.Hide()
            self.ref_audio_panel.Hide()
        self.params_panel.Layout()
        print(f"Selected TTS model: {self.selected_tts_model}")

    def on_select_ref_audio(self, event):
        """Handle reference audio file selection for voice cloning."""
        wildcard = "Audio files (*.mp3;*.wav;*.m4a;*.flac)|*.mp3;*.wav;*.m4a;*.flac"
        with wx.FileDialog(
            self,
            "Select Reference Audio for Voice Cloning",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            self.ref_audio_path = dialog.GetPath()
            # Show just the filename
            filename = Path(self.ref_audio_path).name
            self.ref_audio_text_ctrl.SetValue(filename)
            print(f"Selected reference audio: {self.ref_audio_path}")

    def open_epub(self, file_path):
        # Cleanup previous layout
        if hasattr(self, "selected_book") and self.selected_book:
            self.splitter.DestroyChildren()

        # Hide welcome panel, show splitter
        self.welcome_panel.Hide()
        self.splitter.Show()

        self.selected_file_path = file_path
        print(
            f"Opening file: {file_path}"
        )  # Do something with the filepath (e.g., parse the EPUB)

        from ebooklib import epub
        from audiblez.core import (
            find_document_chapters_and_extract_texts,
            find_good_chapters,
            find_cover,
        )

        book = epub.read_epub(file_path)
        meta_title = book.get_metadata("DC", "title")
        self.selected_book_title = meta_title[0][0] if meta_title else ""
        meta_creator = book.get_metadata("DC", "creator")
        self.selected_book_author = meta_creator[0][0] if meta_creator else ""
        self.selected_book = book

        self.document_chapters = find_document_chapters_and_extract_texts(book)
        good_chapters = find_good_chapters(self.document_chapters)
        self.selected_chapter = good_chapters[0]
        for chapter in self.document_chapters:
            chapter.short_name = (
                chapter.get_name()
                .replace(".xhtml", "")
                .replace("xhtml/", "")
                .replace(".html", "")
                .replace("Text/", "")
            )
            chapter.is_selected = chapter in good_chapters

        self.create_layout_for_ebook(self.splitter)

        # Update Cover
        cover = find_cover(book)
        if cover is not None:
            pil_image = Image.open(io.BytesIO(cover.content))
            wx_img = wx.EmptyImage(pil_image.size[0], pil_image.size[1])
            wx_img.SetData(pil_image.convert("RGB").tobytes())
            cover_h = 200
            cover_w = int(cover_h * pil_image.size[0] / pil_image.size[1])
            wx_img.Rescale(cover_w, cover_h)
            self.cover_bitmap.SetBitmap(wx_img.ConvertToBitmap())
            self.cover_bitmap.SetMaxSize((200, cover_h))

        chapters_panel = self.create_chapters_table_panel(good_chapters)

        #  chapters_panel to left_sizer, or replace if it exists already
        if self.chapters_panel:
            self.left_sizer.Replace(self.chapters_panel, chapters_panel)
            self.chapters_panel.Destroy()
            self.chapters_panel = chapters_panel
        else:
            self.left_sizer.Add(chapters_panel, 1, wx.ALL | wx.EXPAND, 5)
            self.chapters_panel = chapters_panel

        # These two are very important:
        self.splitter_left.Layout()
        self.splitter_right.Layout()
        self.splitter.Layout()

        # Force the main frame to recalculate layout and maximize
        self.Layout()
        self.Maximize(True)

    def on_table_checked(self, event):
        self.document_chapters[event.GetIndex()].is_selected = True

    def on_table_unchecked(self, event):
        self.document_chapters[event.GetIndex()].is_selected = False

    def on_table_selected(self, event):
        chapter = self.document_chapters[event.GetIndex()]
        print("Selected", event.GetIndex(), chapter.short_name)
        self.selected_chapter = chapter
        self.text_area.SetValue(chapter.extracted_text)
        self.chapter_label.SetLabel(
            f'Edit / Preview content for section "{chapter.short_name}":'
        )

    def create_chapters_table_panel(self, good_chapters):
        panel = ScrolledPanel(
            self.splitter_left, -1, style=wx.TAB_TRAVERSAL | wx.SUNKEN_BORDER
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        self.table = table = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        table.InsertColumn(0, "Included")
        table.InsertColumn(1, "Chapter Name")
        table.InsertColumn(2, "Chapter Length")
        table.InsertColumn(3, "Status")
        table.SetColumnWidth(0, 80)
        table.SetColumnWidth(1, 150)
        table.SetColumnWidth(2, 150)
        table.SetColumnWidth(3, 100)
        table.SetSize((250, -1))
        table.EnableCheckBoxes()
        table.Bind(wx.EVT_LIST_ITEM_CHECKED, self.on_table_checked)
        table.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self.on_table_unchecked)
        table.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_table_selected)

        for i, chapter in enumerate(self.document_chapters):
            auto_selected = chapter in good_chapters
            table.Append(["", chapter.short_name, f"{len(chapter.extracted_text):,}"])
            if auto_selected:
                table.CheckItem(i)

        title_text = wx.StaticText(
            panel, label=f"Select chapters to include in the audiobook:"
        )
        sizer.Add(title_text, 0, wx.ALL, 5)
        sizer.Add(table, 1, wx.ALL | wx.EXPAND, 5)
        return panel

    def get_selected_voice(self):
        return self.selected_voice.split(" ")[1]

    def get_selected_speed(self):
        return float(self.selected_speed)

    def on_preview_chapter(self, event):
        button = event.GetEventObject()
        button.SetLabel("⏳")
        button.Disable()

        def generate_preview():
            import audiblez.core as core

            core.load_spacy()

            # Use the factory function to create pipeline based on selected engine
            pipeline = core.create_tts_pipeline(
                engine=self.selected_tts_model,
                voice=self.get_selected_voice(),
                ref_audio=getattr(self, "ref_audio_path", None),
                ref_text=None,
            )

            text = self.selected_chapter.extracted_text[:300]
            if len(text) == 0:
                button.SetLabel("🔊 Preview")
                button.Enable()
                return
            audio_segments = core.gen_audio_segments(
                pipeline,
                text,
                voice=self.get_selected_voice(),
                speed=self.get_selected_speed(),
            )
            if audio_segments:
                final_audio = np.concatenate(audio_segments)
                tmp_preview_wav_file = NamedTemporaryFile(suffix=".wav", delete=False)
                soundfile.write(tmp_preview_wav_file, final_audio, core.sample_rate)
                cmd = ["ffplay", "-autoexit", "-nodisp", tmp_preview_wav_file.name]
                subprocess.run(cmd)
            button.SetLabel("🔊 Preview")
            button.Enable()

        if len(self.preview_threads) > 0:
            for thread in self.preview_threads:
                thread.join()
            self.preview_threads = []
        thread = threading.Thread(target=generate_preview)
        thread.start()
        self.preview_threads.append(thread)

    def on_start(self, event):
        self.synthesis_in_progress = True
        file_path = self.selected_file_path
        voice = self.selected_voice.split(" ")[1]  # Remove the flag
        speed = float(self.selected_speed)
        selected_chapters = [
            chapter for chapter in self.document_chapters if chapter.is_selected
        ]
        self.start_button.Disable()
        self.params_panel.Disable()

        self.table.EnableCheckBoxes(False)
        for chapter_index, chapter in enumerate(self.document_chapters):
            if chapter in selected_chapters:
                self.set_table_chapter_status(chapter_index, "Planned")
                self.table.SetItem(chapter_index, 0, "✔️")

        # Sanitize book title for folder name
        safe_title = "".join(
            [
                c
                for c in self.selected_book_title
                if c.isalpha() or c.isdigit() or c in " ._-"
            ]
        ).strip()

        if not safe_title:
            safe_title = Path(file_path).stem

        output_base = self.output_folder_text_ctrl.GetValue()
        output_folder = str(Path(output_base) / safe_title)
        print(f"Outputting to folder: {output_folder}")

        # self.stop_button.Show()
        print(
            "Starting Audiobook Synthesis",
            dict(file_path=file_path, voice=voice, pick_manually=False, speed=speed),
        )
        self.core_thread = CoreThread(
            params=dict(
                file_path=file_path,
                voice=voice,
                pick_manually=False,
                speed=speed,
                output_folder=output_folder,
                selected_chapters=selected_chapters,
                engine=self.selected_tts_model,
                ref_audio=getattr(self, "ref_audio_path", None),
            )
        )
        self.core_thread.start()

    def on_open(self, event):
        with wx.FileDialog(
            self,
            "Open EPUB File",
            wildcard="*.epub",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_CANCEL:
                return
            file_path = dialog.GetPath()
            print(f"Selected file: {file_path}")
            if not file_path:
                print("No filepath?")
                return
            if self.synthesis_in_progress:
                wx.MessageBox(
                    "Audiobook synthesis is still in progress. Please wait for it to finish.",
                    "Audiobook Synthesis in Progress",
                )
            else:
                wx.CallAfter(self.open_epub, file_path)

    def on_exit(self, event):
        self.Close()

    def set_table_chapter_status(self, chapter_index, status):
        self.table.SetItem(chapter_index, 3, status)

    def open_folder_with_explorer(self, folder_path):
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", folder_path])
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", folder_path])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folder_path])
        except Exception as e:
            print(e)


class CoreThread(threading.Thread):
    def __init__(self, params):
        super().__init__()
        self.params = params

    def run(self):
        import core

        core.main(**self.params, post_event=self.post_event)

    def post_event(self, event_name, **kwargs):
        # eg. 'EVENT_CORE_PROGRESS' -> EventCoreProgress, EVENT_CORE_PROGRESS
        EventObject, EVENT_CODE = EVENTS[event_name]
        event_object = EventObject()
        for k, v in kwargs.items():
            setattr(event_object, k, v)
        wx.PostEvent(wx.GetApp().GetTopWindow(), event_object)


def main():
    print("Starting GUI...")
    app = wx.App(False)
    frame = MainWindow(None, "Audiblez - Generate Audiobooks from E-books")
    frame.Show(True)
    frame.Layout()
    app.SetTopWindow(frame)
    print("Done.")
    app.MainLoop()


if __name__ == "__main__":
    main()
