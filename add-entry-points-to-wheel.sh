#!/bin/bash

# Add additional entry points into the entry-points.txt file

DISTR_INFO_DIR=$1.dist-info
WHL_FILE_PATH=$2
ENTRY_POINTS_VALUES=$3


ENTRY_POINTS_PATH="$DISTR_INFO_DIR/entry_points.txt"
RECORD_PATH="$DISTR_INFO_DIR/RECORD"



#cd $(dirname $0)

echo `ls -a`

echo `ls ../`


mkdir $DISTR_INFO_DIR

unzip -p $WHL_FILE_PATH $ENTRY_POINTS_PATH >  $ENTRY_POINTS_PATH > /dev/null 2>&1

unzip -p $WHL_FILE_PATH $RECORD_PATH >>  $RECORD_PATH

[ ! -s $ENTRY_POINTS_PATH ] || echo -e "\n" >> $ENTRY_POINTS_PATH

printf $"$ENTRY_POINTS_VALUES" >> $ENTRY_POINTS_PATH

ENTRY_POINTS_SIZE=`wc -c $ENTRY_POINTS_PATH | awk '{print $1}'`
ENTRY_POINTS_HASH=`python3 file_hash.py $ENTRY_POINTS_PATH`

sed -i "/^${ENTRY_POINTS_PATH//\//\\/}/d" $RECORD_PATH
echo "$ENTRY_POINTS_PATH,$ENTRY_POINTS_HASH,$ENTRY_POINTS_SIZE" >> $RECORD_PATH

zip $WHL_FILE_PATH $ENTRY_POINTS_PATH
zip $WHL_FILE_PATH $RECORD_PATH

cp $WHL_FILE_PATH $4

rm -r $DISTR_INFO_DIR
