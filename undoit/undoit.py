#!/usr/bin/env python3

import os
import os.path
import shutil

from lxml.html import fromstring, tostring
from hashlib import sha256

# Hardcode the names of tutors here
tutor_names= ['Alice', 'Bob']

class DoItParser(object):
    def __init__(self, main_div):
        self.answers= dict()
        self.names= dict()

        self.parse_toplevel(main_div)

    @staticmethod
    def from_string(string):
        document = fromstring(string)

        main_div= document.cssselect('body>div>div>div')[2]

        return(DoItParser(main_div))

    @staticmethod
    def from_file(path='index.html'):
        with open(path, 'rb') as f:
            content= f.read()

        return(DoItParser.from_string(content))

    def parse_answers(self, task, nick, div):
        for ul in div:
            if task not in self.answers:
                self.answers[task]= dict()

            if nick not in self.answers[task]:
                self.answers[task][nick]= dict()

            if ul[0].text == 'Antwort:':
                if 'inline' not in self.answers[task][nick]:
                    self.answers[task][nick]['inline']= list()

                self.answers[task][nick]['inline'].append(tostring(ul[2]))

            elif ul[0].text == 'Dateien vom Studierenden:':
                if 'files' not in self.answers[task][nick]:
                    self.answers[task][nick]['files']= list()

                for li in ul[2]:
                    if li[0].tag == 'a':
                        href= li[0].attrib['href']
                        self.answers[task][nick]['files'].append(href)

                    else:
                        raise(Exception('unkown li level node'))

            else:
                raise(Exception('unkown upload level node'))

    def parse_blockquotes(self, task, bqs):
        # Content
        for bq in bqs:
            if len(bq)>=2 and bq[0].tag == 'div' and bq[1].tag == 'div':
                (name, nick)= bq[0].text.split('\n')[1].rsplit(' ', 1)
                name= name.strip()
                nick= nick.strip('()')

                self.names[nick]= name

                self.parse_answers(task, nick, bq[1])
            elif len(bq)<=1:
                pass
            else:
                raise(Exception('unkown blockquote level node'))

    def parse_toplevel(self, main_div):
        cur_task= 'unknown'

        for tl_elem in main_div:
            if 'style' in tl_elem.attrib:
                # Useless header
                pass
            elif len(tl_elem) >= 2 and tl_elem[0].tag == 'span' and tl_elem[1].tag == 'br':
                # Task name
                cur_task= tl_elem[0].text
            elif len(tl_elem) and tl_elem[0].tag == 'blockquote':
                self.parse_blockquotes(cur_task, tl_elem)
            else:
                raise(Exception('Unkown top level node'))

class TutorMapper(object):
    def __init__(self, tutors):
        self.tutors= tutors

    def __call__(self, nick):
        numtutors= len(self.tutors)

        chash= sha256(nick.encode('utf-8')).digest()
        thash= sum(v<<(8*e) for (e, v) in enumerate(chash[:4]))

        return(self.tutors[thash%numtutors])

def main():
    index= DoItParser.from_file()

    tutmap= TutorMapper(tutor_names)

    for (task_name, task_answers) in index.answers.items():
        for (nick_name, nick_answers) in task_answers.items():
            resp_tutor= tutmap(nick_name)

            folder= os.path.join('submissions', resp_tutor, task_name, nick_name)
            os.makedirs(folder, exist_ok=True)

            if 'inline' in nick_answers:
                for (num, content) in enumerate(nick_answers['inline']):
                    fname= os.path.join(folder, 'inline_{}.html'.format(num))

                    with open(fname, 'wb') as fd_il:
                        fd_il.write(content)

            if 'files' in nick_answers:
                src_dirname= os.path.dirname(nick_answers['files'][0])
                src_dir_list= sorted(os.listdir(src_dirname))

                # Filename encoding is broken in .zip
                # build a map from broken encoding > intact encoding
                dst_dir_list= sorted(map(os.path.basename, nick_answers['files']))

                for (src, dst) in zip(src_dir_list, dst_dir_list):
                    src_path= os.path.join(src_dirname, src)
                    dst_path= os.path.join(folder, dst.split('_', 1)[1])

                    shutil.copy(src_path, dst_path)

                    if dst.endswith('.zip'):
                        shutil.unpack_archive(dst_path, folder)

if __name__ == '__main__':
    main()
