$latex = 'platex -kanji=utf-8 -synctex=1 -interaction=nonstopmode %O %S';
$bibtex = 'pbibtex';
$dvipdf = 'dvipdfmx %O -o %D %S';
$makeindex = 'mendex %O -o %D %S';
$pdf_mode = 3;
$ENV{TZ} = 'Asia/Tokyo';
#$ENV{OPENTYPEFONTS} = '/usr/share/fonts//:';
#$ENV{TTFONTS} = '/usr/share/fonts//:';
