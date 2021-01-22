import csv
import yaml
import re
import os
from os import path
import sys
import argparse

config = {}
schemas = {}
regex = re.compile('[^a-zA-Z]')

#TODO: Improve schema comparing to consider inner object's properties
def schemaEquals(s1, s2):
    if len(s1['properties']) != len(s2['properties']):
        return False
    for prop in s1['properties'].keys():
        if prop not in s2['properties']:
            return False
    return True

def setRequired(schema):
    requireds = []
    for prop in schema['properties'].keys():
        if '_required' in schema['properties'][prop]:
            schema['properties'][prop].pop('_required')
            requireds.append(prop)
    if len(requireds) > 0:
        schema['required'] = requireds

def createProperty(propName, obj, baseName):
    name = f'{baseName}{propName[0].upper() + propName[1:]}'
    if obj['_type'] == 'object':
        ref = createObject(obj, name, propName)
        return {
            '$ref': f'./{ref}.yaml'
        }
    elif obj['_type'] == 'array':
        ref = createObject(obj, name, propName)
        temp = {
            'type': 'array',
            'items': {
                '$ref': f'./{ref}.yaml'
            }
        }
        if 'maxItems' in obj:
            temp['maxItems'] = int(obj['maxItems'])
        if 'minItems' in obj:
            temp['minItems'] = int(obj['minItems'])
        if 'description' in obj:
            temp['description'] = obj['description']
        return temp
    else:
        obj['type'] = obj['_type']
        obj.pop('_type')
        return obj

def createObject(obj, name, baseName: str = ''):
    schema = {
        'type': 'object',
        'properties': {}
    }
    if 'description' in obj:
        schema['description'] = obj['description']
    for key in obj.keys():
        if key in ['_type', 'maxItems', 'description', 'minItems']:
            continue
        prop = createProperty(key, obj[key], name)
        schema['properties'][key] = prop
    
    setRequired(schema)

    if baseName:
        baseName = baseName[0].upper() + baseName[1:]
        if baseName not in schemas:
            schemas[baseName] = []
        included = False
        for s in schemas[baseName]:
            if schemaEquals(s['schema'], schema):
                s['names'].append(name)
                included = True
                break
        if not included:
            schemas[baseName].append({
                'names': [name],
                'schema': schema
            })
    
    outputfile = os.path.join(config['outputFolder'], f'{name}.yaml')
    print(f'Saving schema {name} in: {outputfile}')
    with open(outputfile, 'w', encoding='utf-8',) as file:
        yaml.safe_dump(schema, file, allow_unicode=True, width=100000)
    
    return name

def types(type: str):
    return {
        'Texto': 'string',
        'Objeto': 'object',
		'objeto': 'object',
        'object': 'object',
        'Lista': 'array'

    }.get(type, 'string')

def convertType(type: str):
    type = regex.sub('', type)
    return types(type)

def cleanEnums(enums):
    enums = enums.rstrip('\n').rstrip(';')
    if ';' in enums:
        sep = ';'
    else:
        sep = '\n'
    parts = enums.split(sep)
    return [value.strip().rstrip('\n').replace("'",'') for value in parts if value]

def exec(parts: list, node, row):
    size = len(parts)
    if parts[0]:
        parts[0] = parts[0][0].lower() + parts[0][1:].replace('\n', '')
        if parts[0] not in node:
            node[parts[0]] = {}
            if size > 1:
                node[parts[0]]['_type'] = 'object'

        if size > 1:
            exec(parts[1:], node[parts[0]], row)
        else:
            node[parts[0]]['_type'] = convertType(row['Tipo do Dado'])
            if 'Formato' in row and row['Formato']:
                node[parts[0]]['pattern'] = row['Formato'].replace('\n', '')
            if node[parts[0]]['_type'] == 'string' and row['Domínio']:
                node[parts[0]]['enum'] = cleanEnums(row['Domínio'])
            if row['Definição']:
                node[parts[0]]['description'] = row['Definição'].rstrip('\n').rstrip(' ')
            if row['Tamanho']:
                node[parts[0]]['maxLength'] = int(row['Tamanho'])
            if row['Tipo do Dado'] == 'Lista':
                if row['Máximo de Ocorrências'].isnumeric():
                    node[parts[0]]['maxItems'] = int(row['Máximo de Ocorrências'])
                if row['Mínimo de Ocorrências'].isnumeric() and int(row['Mínimo de Ocorrências']) > 0:
                    node[parts[0]]['minItems'] = int(row['Mínimo de Ocorrências'])
            if row['Mandatoriedade'] == 'Obrigatório':
                node[parts[0]]['_required'] = True
        

def parseCsv(path):
    rows = []
    with open(path, 'r', encoding='utf-8-sig') as csvfile:
        spamreader = csv.DictReader(csvfile, delimiter=';', quotechar='"')
        for row in spamreader:
            rows.append(row)
    return rows

def generateSchemas(rows, name):  
    tree = {}
    for row in rows:
        if name.upper() in row['Xpath'].upper():
            if row['Xpath'].rstrip('/').upper().endswith(name.upper()):
                continue
            parts = row['Xpath'].rstrip('/').split('/')
            index = list(map(lambda p: p.upper(), parts)).index(name.upper())
            exec(parts[index + 1:], tree, row)
    createObject(tree, name, name)

def schemaNameFromFilePath(filePath):
    fileName, fileExtension = os.path.splitext(os.path.basename(filePath))
    parts = fileName.split('_')
    name = ' '.join(parts).title().replace(' ', '')
    return {
        'automated_teller_machines': 'SharedAutomatedTellerMachines'
    }.get(fileName, name)

def processFile(path):
    print(f'Processing file: {path}...')
    
    rows = parseCsv(path)
    generateSchemas(rows, schemaNameFromFilePath(path))
    
    print('File processed with success!')

def main(args):
    dirDicts = args.dictionariesPath
    config['outputFolder'] = args.ouputPath
    
    print('Checking dictionaries folder...')
    if not path.exists(dirDicts):
        print(f'Folder containing the dictionaries does not exist! {dirDicts}')
        sys.exit(1)

    print('Checking schemas output folder...')
    os.makedirs(config['outputFolder'], exist_ok=True)
    
    for file in os.listdir(dirDicts):
        processFile(os.path.join(dirDicts, file))

def parseArgs():
    parser = argparse.ArgumentParser(description = '''Generate schemas from csv dictionaries. 
    A report with created schemas is generated in current folder.''')
    
    parser.add_argument('--dictionariesPath', required = True, help = 'The folder containing the dictionaries to be parsed.')
    parser.add_argument('--ouputPath', required = True, help = 'The folder where the schemas will be generated.')
    return parser.parse_args()

def generateReport():
    with open("report.yaml", 'w', encoding='utf-8',) as file:
        yaml.safe_dump(schemas, file, allow_unicode=True, width=100000)

if __name__=="__main__":
    args = parseArgs()
    main(args)
    generateReport()
