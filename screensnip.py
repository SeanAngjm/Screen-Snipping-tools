import tkinter as tk
from tkinter import filedialog
from PIL import ImageTk, Image, ImageDraw
import threading
import keyboard
import mss
import numpy as np
import ctypes

class ScreenSnipApp:
    def __init__(self):
        self.highlight_colour = (255, 255, 0, 80)  # default yellow
        self.image_window = None
        self.highlight_mode = False
        self.image = None
        self.overlay = None
        self.highlight_strokes = []
        self.current_stroke = []
        self.full_screen_image = None
        self.virtual_screen_offset = (0, 0)

        threading.Thread(target=self.listen_hotkey, daemon=True).start()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.mainloop()

    def listen_hotkey(self):
        keyboard.add_hotkey("alt+prtscn", self.start_snip)

    def start_snip(self):
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # All monitors
            self.virtual_screen_offset = (monitor["left"], monitor["top"])
            img_np = np.array(sct.grab(monitor))
            b, g, r, a = img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2], img_np[:, :, 3]
            rgb_img = np.dstack([r, g, b])
            self.full_screen_image = Image.fromarray(rgb_img)

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        screen_width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        screen_height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        self.screen_left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        self.screen_top = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN

        self.snip_window = tk.Toplevel()
        self.snip_window.geometry(f"{screen_width}x{screen_height}+{self.screen_left}+{self.screen_top}")
        self.snip_window.attributes("-alpha", 0.3)
        self.snip_window.config(bg="gray")
        self.snip_window.attributes("-topmost", True)
        self.snip_window.resizable(False, False)
        self.snip_window.overrideredirect(True)


        self.canvas = tk.Canvas(self.snip_window, cursor="cross", bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.start_x = None
        self.start_y = None
        self.rect = None

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

    def on_mouse_down(self, event):
        self.start_x = self.snip_window.winfo_pointerx()
        self.start_y = self.snip_window.winfo_pointery()
        self.rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='red', width=2)

    def on_mouse_drag(self, event):
        cur_x = self.snip_window.winfo_pointerx()
        cur_y = self.snip_window.winfo_pointery()
        start_x_win = self.start_x - self.snip_window.winfo_rootx()
        start_y_win = self.start_y - self.snip_window.winfo_rooty()
        cur_x_win = cur_x - self.snip_window.winfo_rootx()
        cur_y_win = cur_y - self.snip_window.winfo_rooty()
        self.canvas.coords(self.rect, start_x_win, start_y_win, cur_x_win, cur_y_win)

    def on_mouse_up(self, event):
        end_x = self.snip_window.winfo_pointerx()
        end_y = self.snip_window.winfo_pointery()
        self.snip_window.destroy()

        left = min(self.start_x, end_x) - self.virtual_screen_offset[0]
        top = min(self.start_y, end_y) - self.virtual_screen_offset[1]
        right = max(self.start_x, end_x) - self.virtual_screen_offset[0]
        bottom = max(self.start_y, end_y) - self.virtual_screen_offset[1]

        bbox = (left, top, right, bottom)
        self.image = self.full_screen_image.crop(bbox)
        self.show_image(self.image)

    def show_image(self, image):
        if self.image_window is not None and self.image_window.winfo_exists():
            self.image_window.destroy()

        self.image_window = tk.Toplevel()
        self.image_window.title("Snip")
        self.image_window.attributes('-topmost', True)
        self.image_window.resizable(True, True)

        # Scrollable canvas setup
        container = tk.Frame(self.image_window)
        container.pack(fill=tk.BOTH, expand=True)

        h_scroll = tk.Scrollbar(container, orient=tk.HORIZONTAL)
        v_scroll = tk.Scrollbar(container, orient=tk.VERTICAL)
        self.canvas_img = tk.Canvas(container, 
                                    xscrollcommand=h_scroll.set, 
                                    yscrollcommand=v_scroll.set,
                                    bg='white')

        h_scroll.config(command=self.canvas_img.xview)
        v_scroll.config(command=self.canvas_img.yview)

        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas_img.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Bind scroll wheel
        self.canvas_img.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas_img.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)

        # Display image
        self.tk_image = ImageTk.PhotoImage(image)
        self.canvas_img.create_image(0, 0, anchor="nw", image=self.tk_image)
        self.canvas_img.config(scrollregion=(0, 0, image.width, image.height))

        # Create overlay
        self.overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        self.overlay_tk = ImageTk.PhotoImage(self.overlay)
        self.overlay_id = self.canvas_img.create_image(0, 0, anchor="nw", image=self.overlay_tk)

        # Bind context and draw tools
        self.canvas_img.bind("<Button-3>", self.show_context_menu)
        self.canvas_img.bind("<ButtonPress-1>", self.start_stroke)
        self.canvas_img.bind("<B1-Motion>", self.draw_highlight)
        self.canvas_img.bind("<ButtonRelease-1>", self.end_stroke)

        self.image_window.geometry(f"{min(image.width, 1000)}x{min(image.height, 800)}+100+100")

    def _on_mousewheel(self, event):
        self.canvas_img.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self.canvas_img.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def show_context_menu(self, event):
        menu = tk.Menu(self.image_window, tearoff=0)
        menu.add_command(label="Toggle Highlighter", command=self.toggle_highlight)
        menu.add_command(label="Undo Last Highlight", command=self.undo_highlight)
        menu.add_command(label="Save as JPG", command=self.save_image)
        menu.add_command(label="Highlighter Colour", command=self.colour_highlight)
        menu.tk_popup(event.x_root, event.y_root)

    def toggle_highlight(self):
        self.highlight_mode = not self.highlight_mode

    def start_stroke(self, event):
        if self.highlight_mode:
            self.current_stroke = []

    def draw_highlight(self, event):
        if self.highlight_mode:
            x, y = event.x, event.y
            if self.current_stroke:
                last_x, last_y = self.current_stroke[-1]
                draw = ImageDraw.Draw(self.overlay)
                draw.line([last_x, last_y, x, y], fill=self.highlight_colour, width=15)
            self.current_stroke.append((x, y))
            self.overlay_tk = ImageTk.PhotoImage(self.overlay)
            self.canvas_img.itemconfig(self.overlay_id, image=self.overlay_tk)


    def end_stroke(self, event):
        if self.highlight_mode and self.current_stroke:
            self.highlight_strokes.append(list(self.current_stroke))
            self.current_stroke = []

    def undo_highlight(self):
        if self.highlight_strokes:
            self.highlight_strokes.pop()
            self.overlay = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(self.overlay)
            for stroke in self.highlight_strokes:
                for ellipse in stroke:
                    draw.ellipse(ellipse, fill=self.highlight_colour)
            self.overlay_tk = ImageTk.PhotoImage(self.overlay)
            self.canvas_img.itemconfig(self.overlay_id, image=self.overlay_tk)

    def colour_highlight(self):
        if not self.highlight_mode:
            return

        color_menu = tk.Menu(self.image_window, tearoff=0)

        def set_colour(name):
            colors = {
                "Yellow": (255, 255, 0, 80),
                "Blue": (0, 0, 255, 80),                                                                                
                "Green": (0, 255, 0, 80),
                "Red": (255, 0, 0, 80),
                "Orange": (255, 165, 0, 80),
                "Purple": (128, 0, 128, 80),
            }
            self.highlight_colour = colors[name]

        for color in ["Yellow", "Blue", "Green", "Red", "Orange", "Purple"]:
            color_menu.add_command(label=color, command=lambda c=color: set_colour(c))

        color_menu.tk_popup(self.image_window.winfo_pointerx(), self.image_window.winfo_pointery())

    def save_image(self):
        if self.image:
            combined = Image.alpha_composite(self.image.convert("RGBA"), self.overlay)
            file_path = filedialog.asksaveasfilename(defaultextension=".jpg",
                                                     filetypes=[("JPEG files", "*.jpg")])
            if file_path:
                combined.convert("RGB").save(file_path, "JPEG")

if __name__ == "__main__":
    ScreenSnipApp()
