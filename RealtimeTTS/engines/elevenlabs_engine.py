import io

from elevenlabs import voices, generate, stream
from elevenlabs.api import Voice, VoiceSettings
from typing import Iterator, Union, Optional
from .base_engine import BaseEngine
import elevenlabs
import subprocess
import threading
import logging
import pyaudio
import shutil
import soundfile as sf

class ElevenlabsVoice:
    def __init__(self, name, voice_id, category, description, labels):
        self.name = name
        self.voice_id = voice_id
        self.category = category
        self.description = description
        self.labels = labels

    def __repr__(self):
        label_string = ', '.join(self.labels.values())
        return f"{self.name} ({self.category}, id: {self.voice_id}, {label_string})"

class ElevenlabsEngine(BaseEngine):

    def __init__(self, 
                 api_key: str = "", 
                 voice: str = "Nicole", 
                 id: str = "piTKgcLEGmPE4e6mEKli",
                 category: str = "premade",
                 clarity: float = 75.0,
                 stability: float = 50.0,
                 style_exxageration: float = 0.0,
                 use_speaker_boost: bool = True,
                 model: str = "eleven_multilingual_v1",
                 output_format: str = "pcm_16000"):
        """
        Initializes an elevenlabs voice realtime text to speech engine object.

        Args:
            api_key (str): Elevenlabs API key. (TTS API key)
            voice (str, optional): Voice name. Defaults to "Nicole".
            id (str, optional): Voice ID. Defaults to "piTKgcLEGmPE4e6mEKli".
            category (str, optional): Voice category. Defaults to "premade".
            clarity (float, optional): Clarity / Similarity. Adjusts voice similarity and resemblance. Defaults to "75.0".
            stability (float, optional): Stability. Controls the voice performance, with higher values producing a steadier tone and lower values giving a more emotive output. Defaults to "50.0".
            style_exxageration (float, optional): Style Exxageration. Controls the voice performance, with higher values giving a more emotive output and lower values producing a steadier tone. Defaults to "0.0".
            model (str, optional): Model. Defaults to "eleven_multilingual_v1". Some models may not work with real time inference.
        """

        self.voice_name = voice
        self.id = id
        self.category = category
        self.clarity = clarity
        self.stability = stability
        self.style_exxageration = style_exxageration
        self.model = model
        self.pause_event = threading.Event()
        self.immediate_stop = threading.Event()
        self.on_audio_chunk = None
        self.on_playback_started = False
        self.output_format = output_format
        
        self.set_api_key(api_key)

        self.voice_object = Voice.from_id(self.id)
        self.voice_object.settings = VoiceSettings(
            stability=self.stability / 100,
            similarity_boost=self.clarity / 100,
            style=self.style_exxageration / 100,
            use_speaker_boost=use_speaker_boost
        )
        
    def post_init(self):
        self.engine_name = "elevenlabs"

    def get_stream_info(self):
        """
        Returns the audio stream configuration information suitable for PyAudio.

        Returns:
            tuple: A tuple containing the audio format, number of channels, and the sample rate.
                  - Format (int): The format of the audio stream. pyaudio.paInt16 represents 16-bit integers.
                  - Channels (int): The number of audio channels. 1 represents mono audio.
                  - Sample Rate (int): The sample rate of the audio in Hz. 16000 represents 16kHz sample rate.
        """
        if self.output_format == "pcm_16000":   
            return pyaudio.paInt16, 1, 16000
        elif self.output_format == "ulaw_8000":
            # TODO verify paInt8 or paCustomFormat?
            return pyaudio.paInt8, 1, 8000
        else:
            raise ValueError("Invalid output_format. Supported formats are 'pcm_16000' and 'ulaw_8000'.")

    def synthesize(self, 
                   text: str) -> bool:
        """
        Synthesizes text to audio stream.

        Args:
            text (str): Text to synthesize.
        """

        audio_stream = generate(
            text=text,
            model=self.model,
            voice=self.voice_object,
            stream=True,
            latency=1,
            output_format=self.output_format
            )
        
        for chunk in audio_stream:
            self.queue.put(chunk)

        return True
        
    def set_api_key(self, api_key: str):
        """
        Sets the elevenlabs api key. 

        Args:
            api_key (str): Elevenlabs API key. (TTS API key)
        """
        self.api_key = api_key
        if api_key: 
            elevenlabs.set_api_key(api_key)            
    
    def get_voices(self):
        """
        Retrieves the voices available from the Elevenlabs voice source.

        Calling this takes time, it sends a request to the Elevenlabs API to fetch the list of available voices.
        This method fetches the list of available voices using the elevenlabs `voices()` function and then
        constructs a list of `ElevenlabsVoice` objects to represent each voice's details.       

        Returns:
            list[ElevenlabsVoice]: A list containing ElevenlabsVoice objects representing each available voice. 
                                Each ElevenlabsVoice object encapsulates information such as the voice's name, 
                                ID, category, description, and associated labels.

        Note:
            This method relies on the `voices()` function to obtain the raw voice data. Ensure that the 
            `voices()` function is accessible and functional before calling this method.
        """        
        fetched_voices = voices()

        voice_objects = []
        for voice in fetched_voices:
            voice_object = ElevenlabsVoice(voice.name, voice.voice_id, voice.category, voice.description, voice.labels)
            voice_objects.append(voice_object)
        return voice_objects
    
    def set_voice(self, voice: Union[str, ElevenlabsVoice]):
        """
        Sets the voice to be used for speech synthesis.

        Args:
            voice (Union[str, ElevenlabsVoice]): The voice to be used for speech synthesis.
        """
        if isinstance(voice, ElevenlabsVoice):
            logging.info(f"Setting voice to {voice.name}")
            self.voice_name = voice.name
            self.id = voice.voice_id
            self.category = voice.category
            return
        else:
            installed_voices = self.get_voices()
            for installed_voice in installed_voices:
                if voice in installed_voice.name:
                    logging.info(f"Setting voice to {installed_voice.name}")
                    self.voice_name = installed_voice.name
                    self.id = installed_voice.voice_id
                    self.category = installed_voice.category
                    return
                
        logging.warning(f"Voice {voice} not found.")

    def set_voice_parameters(self, **voice_parameters):
        """
        Sets the voice parameters to be used for speech synthesis.

        Args:
            **voice_parameters: The voice parameters to be used for speech synthesis.
        """
        if 'clarity' in voice_parameters:
            self.clarity = voice_parameters['clarity']
        if 'stability' in voice_parameters:
            self.stability = voice_parameters['stability']
        if 'style_exxageration' in voice_parameters:
            self.style_exxageration = voice_parameters['style_exxageration']