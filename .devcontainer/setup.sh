#!/bin/bash
echo "🔧 Setting up ASMR Backend..."
sudo apt update
sudo apt install -y ffmpeg sox
pip3 install flask flask-cors

mkdir -p /workspaces/asmr-backend/{uploads,outputs,ambient,temp}
cd /workspaces/asmr-backend/ambient

echo "🌧️ Generating ambient sounds..."
ffmpeg -y -f lavfi -i "anoisesrc=d=60:c=white:r=44100:a=0.05" -af "lowpass=f=2000,highpass=f=200" -t 60 rain.mp3 2>/dev/null
ffmpeg -y -f lavfi -i "anoisesrc=d=60:c=pink:r=44100:a=0.03" -af "lowpass=f=800" -t 60 wind.mp3 2>/dev/null
ffmpeg -y -f lavfi -i "anoisesrc=d=60:c=brown:r=44100:a=0.08" -af "lowpass=f=500" -t 60 ocean.mp3 2>/dev/null
ffmpeg -y -f lavfi -i "anoisesrc=d=60:c=white:r=44100:a=0.02" -af "highpass=f=1000,lowpass=f=5000,volume=0.5" -t 60 fire.mp3 2>/dev/null
ffmpeg -y -f lavfi -i "sine=frequency=4500:duration=60" -af "tremolo=f=8:d=0.5,volume=0.15" -t 60 night.mp3 2>/dev/null
ffmpeg -y -f lavfi -i "sine=frequency=528:duration=60" -af "tremolo=f=0.5:d=0.3" -t 60 bowl.mp3 2>/dev/null

echo "✅ Backend Ready!"
