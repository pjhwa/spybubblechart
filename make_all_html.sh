#!/bin/bash

TODAY=$(date +%Y-%m-%d)

for period in 1d 5d 1mo ytd 1y
do
	python3 sp500_bubble_chart.py --period $period --end_date $TODAY
done
