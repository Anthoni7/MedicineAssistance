import os
import traceback
import cv2
import numpy as np
from PIL import Image, ImageTk
import pytesseract
from gtts import gTTS
import tkinter as tk
from tkinter import messagebox, filedialog
import threading
from playsound import playsound
import uuid
import sqlite3
import time
import datetime
from tkinter import ttk

# Initialize directories
input_dir = "C:/Users/HP/Desktop/MY LF/Python Programming"
output_dir = os.path.join(input_dir, "Processed")
os.makedirs(output_dir, exist_ok=True)


# Database initialization
def initialize_database():
    conn = sqlite3.connect("medilenz.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medicines (
            medicine_name TEXT PRIMARY KEY,
            description TEXT
        )
    """)
    conn.commit()

    # Insert sample data if the table is empty
    cursor.execute("SELECT COUNT(*) FROM medicines")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO medicines (medicine_name, description) VALUES (?, ?)",
            [
                ("aspirin",
                 "This medication provides both pain relief and anti-inflammatory benefits. Take 300 to 1000 milligrams every four to six hours as needed."),
                ("ibuprofen",
                 "Ibuprofen is used for pain relief and as an anti-inflammatory. The recommended dosage is 200-400 mg every 4-6 hours."),
                ("paracetamol",
                 "These medicines can help relieve pain and reduce fever, making you feel more comfortable. You should take 500 to 1000 milligrams every 4 to 6 hours, depending on your condition."),
            ]
        )
        conn.commit()
    conn.close()


# Lock for ensuring no overlapping speech
voice_lock = threading.Lock()


# Function to speak the text using gTTS
def speak_with_gtts(text):
    def play_audio():
        try:
            with voice_lock:
                unique_filename = f"output_{uuid.uuid4().hex}.mp3"
                tts = gTTS(text, lang='en', slow=False)
                tts.save(unique_filename)
                playsound(unique_filename)
        finally:
            if os.path.exists(unique_filename):
                os.remove(unique_filename)

    threading.Thread(target=play_audio).start()


# Function to process an image and extract text
def process_image(file_path, output_dir):
    try:
        img = cv2.imread(file_path)
        if img is None:
            print(f"Error: Unable to load image at {file_path}")
            return None

        original_img = img.copy()
        original_height, original_width = img.shape[:2]
        max_dim = 1000
        scaling_factor = max_dim / max(original_height, original_width)
        img = cv2.resize(img, (int(original_width * scaling_factor), int(original_height * scaling_factor)))
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edged = cv2.Canny(blurred, 75, 200)
        thresh = cv2.threshold(gray, 225, 255, cv2.THRESH_BINARY_INV)[1]

        cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if len(cnts) == 2 else cnts[1]
        H, W = img.shape[:2]
        selected_cnt = None
        for cnt in cnts:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            aspect_ratio = w / h
            if area > 100 and (0.5 < aspect_ratio < 2.0) and (W / 4 < x + w // 2 < W * 3 / 4) and (
                    H / 4 < y + h // 2 < H * 3 / 4):
                selected_cnt = cnt
                break

        if selected_cnt is None:
            print(f"No suitable contour found for {file_path}")
            return None

        mask = np.zeros(img.shape[:2], np.uint8)
        cv2.drawContours(mask, [selected_cnt], -1, 255, -1)
        mask = cv2.resize(mask, (original_width, original_height))
        dst = cv2.bitwise_and(original_img, original_img, mask=mask)

        gray = cv2.cvtColor(dst, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 3)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        processed_image_path = os.path.join(output_dir, f"{os.path.basename(file_path)[:-4]}-Processed.png")
        cv2.imwrite(processed_image_path, gray)

        file_text = pytesseract.image_to_string(gray, lang='eng')
        text_file_name = os.path.join(output_dir, f"{os.path.basename(file_path)[:-4]}-Extracted.txt")

        if file_text.strip():
            with open(text_file_name, "w", encoding="utf-8") as f:
                f.write(file_text)
            print(f"Text extracted and saved: {text_file_name}")
        else:
            print(f"No text extracted from {file_path}")
        return file_text

    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        traceback.print_exc()
        return None


# Function to handle file selection and processing
def select_file():
    conn = sqlite3.connect("medilenz.db")
    cursor = conn.cursor()

    file_path = filedialog.askopenfilename(filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp")])
    if file_path:
        extracted_text = process_image(file_path, output_dir)
        if extracted_text:
            matched_key = None
            cursor.execute("SELECT medicine_name, description FROM medicines")
            for row in cursor.fetchall():
                if row[0].lower() in extracted_text.lower():
                    matched_key = row[0]
                    medicine_info = row[1]
                    break

            if matched_key:
                result_text = f"\n\nMEDICINE IDENTIFIED:\n{matched_key}\nDETAILS: {medicine_info}\n"
                speak_with_gtts(f"Medicine identified: {matched_key}.")
                speak_with_gtts(f"Details: {medicine_info}.")
            else:
                result_text = f"\n\nMEDICINE IDENTIFIED:\n{extracted_text.strip()}\nDETAILS: No information found in the database.\n"
                speak_with_gtts(f"Medicine identified: {extracted_text.strip()}.")
                speak_with_gtts("No information found in the database.")

            display_extracted_text(result_text)
        else:
            messagebox.showinfo("No Text Found", "No text was extracted from the selected file.")

    conn.close()


# Function to display extracted text in the UI
def display_extracted_text(text):
    text_box.config(state=tk.NORMAL)
    text_box.delete(1.0, tk.END)
    text_box.insert(tk.END, text)
    text_box.config(state=tk.DISABLED)


# Function to load and resize the banner image
def load_banner_image(image_path, window_width):
    banner_image = Image.open(image_path)
    max_banner_height = 150
    scaling_factor = max_banner_height / banner_image.height
    new_width = int(banner_image.width * scaling_factor)
    banner_image = banner_image.resize((new_width, max_banner_height), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(banner_image)


# Reminder window functionality
def open_reminder_window():
    def set_reminder():
        reminder_time = f"{hour_combobox.get()}:{minute_combobox.get()}"
        selected_medicine = medicine_dropdown.get()

        try:
            hour, minute = map(int, reminder_time.split(":"))
            if not (0 <= hour < 24 and 0 <= minute < 60):
                raise ValueError
            if not selected_medicine:
                messagebox.showerror("Error", "Please select a medicine.")
                return

            messagebox.showinfo("Reminder Set", f"Reminder set for {selected_medicine} at {reminder_time}.")
            threading.Thread(target=reminder_thread, args=(hour, minute, selected_medicine)).start()
        except ValueError:
            messagebox.showerror("Error", "Invalid time format. Please enter in HH:MM format.")

    def reminder_thread(hour, minute, medicine_name):
        while True:
            now = datetime.datetime.now()
            if now.hour == hour and now.minute == minute:
                reminder_message = f"Now it's time to take your {medicine_name} medicine. Please have your medicine."
                speak_with_gtts(reminder_message)
                playsound("alarm_sound.mp3")  # Replace with your alarm sound file
                messagebox.showinfo("Reminder", reminder_message)
                break
            time.sleep(30)  # Check every 30 seconds

    reminder_window = tk.Toplevel(root)
    reminder_window.title("Set Reminder")
    reminder_window.geometry("400x300")
    reminder_window.config(bg="white")

    tk.Label(reminder_window, text="Select Medicine:", font=("Arial", 14), bg="white").pack(pady=10)
    conn = sqlite3.connect("medilenz.db")
    cursor = conn.cursor()
    cursor.execute("SELECT medicine_name FROM medicines")
    medicines = [row[0] for row in cursor.fetchall()]
    conn.close()

    medicine_dropdown = ttk.Combobox(reminder_window, values=medicines, font=("Arial", 12))
    medicine_dropdown.pack(pady=10)
    medicine_dropdown.bind("<Enter>", lambda e: on_button_hover(e, medicine_dropdown.get()))  # Hover effect on dropdown

    tk.Label(reminder_window, text="Set Hour (HH):", font=("Arial", 14), bg="white").pack(pady=10)

    # Hour selection combobox (0-23)
    hour_combobox = ttk.Combobox(reminder_window, values=[str(i).zfill(2) for i in range(24)], font=("Arial", 12))
    hour_combobox.pack(pady=0.1)
    hour_combobox.set("00")  # Default to 00 for hours

    tk.Label(reminder_window, text="Set Minute (MM):", font=("Arial", 14), bg="white").pack(pady=10)

    # Minute selection combobox (00-59)
    minute_combobox = ttk.Combobox(reminder_window, values=[str(i).zfill(2) for i in range(60)], font=("Arial", 12))
    minute_combobox.pack(pady=0.1)
    minute_combobox.set("00")  # Default to 00 for minutes

    tk.Button(reminder_window, text="Set Reminder", font=("Arial", 14), bg="#007bff", fg="white",
              command=set_reminder).pack(pady=20)


# Track when the mouse is over the button
button_hover_start_time = {}


# Function to provide voice output when hovering over a button for 1 second
def on_button_hover(event, button_text):
    # Get the current time when the cursor enters the button
    current_time = time.time()

    # Store the start time for this specific button
    button_hover_start_time[event.widget] = current_time

    # Start the 1-second delay to trigger voice output
    def delayed_speak():
        hover_duration = time.time() - button_hover_start_time.get(event.widget, 0)

        # If the cursor has been over the button for 1 second or more
        if hover_duration >= 1:
            speak_with_gtts(button_text)

    # Call the function after 1 second delay
    event.widget.after(1000, delayed_speak)  # Trigger after 1000 ms (1 second)


# Function to cancel voice output if the cursor leaves the button
def on_button_leave(event):
    if event.widget in button_hover_start_time:
        del button_hover_start_time[event.widget]


# Update button binding to use new hover and leave functions
def bind_hover_and_leave(button, text):
    button.bind("<Enter>", lambda event: on_button_hover(event, text))
    button.bind("<Leave>", on_button_leave)


# Create the main UI window
root = tk.Tk()
root.title("MediLens")
root.geometry("800x600")
root.config(bg="white")

# Initialize the database
initialize_database()


# Load and display the banner image
def update_banner_image(event=None):
    window_width = root.winfo_width()
    banner_path = "C:/Users/HP/Desktop/MY LF/Python Programming/output/logo.PNG"
    banner_photo = load_banner_image(banner_path, window_width)
    banner_label.config(image=banner_photo)
    banner_label.image = banner_photo


banner_label = tk.Label(root, bg="white")
banner_label.pack(fill=tk.X)
root.bind("<Configure>", update_banner_image)

# Create and bind hover events for the buttons
select_button = tk.Button(root, text="Select Image File", font=("Arial", 16), bg="#007bff", fg="white",
                          command=select_file)
select_button.pack(pady=20)
bind_hover_and_leave(select_button, select_button.cget("text"))  # Binding hover effect

text_box = tk.Text(root, wrap=tk.WORD, font=("Arial", 12), bg="white", fg="black", padx=10, pady=10, height=10)
text_box.pack(expand=True, fill=tk.BOTH)
text_box.config(state=tk.DISABLED)

button_frame = tk.Frame(root, bg="white")
button_frame.pack(pady=10)

reselect_button = tk.Button(button_frame, text="Reselect", font=("Arial", 14), bg="#28a745", fg="white",
                            command=select_file)
reselect_button.pack(side=tk.LEFT, padx=20)
bind_hover_and_leave(reselect_button, reselect_button.cget("text"))  # Binding hover effect

exit_button = tk.Button(button_frame, text="Exit", font=("Arial", 14), bg="#dc3545", fg="white", command=root.quit)
exit_button.pack(side=tk.LEFT, padx=20)
bind_hover_and_leave(exit_button, exit_button.cget("text"))  # Binding hover effect

reminder_button = tk.Button(root, text="Set Reminder", font=("Arial", 16), bg="#007bff", fg="white",
                            command=open_reminder_window)
reminder_button.pack(pady=20)
bind_hover_and_leave(reminder_button, reminder_button.cget("text"))  # Binding hover effect

root.mainloop()
