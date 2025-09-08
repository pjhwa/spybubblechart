#!/bin/bash

TODAY=$(date +%Y-%m-%d)

for period in 1y ytd 1mo 5d 1d 
do
	python3 sp500_bubble_chart.py --period $period --end_date $TODAY
done
