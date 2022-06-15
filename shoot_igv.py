#!/usr/bin/env python

import click
import isabl_cli as ii
import os
import sys

def get_sample(sample_identifier, verbose):
    sample = ii.get_instances(
            endpoint='samples',
            identifier=sample_identifier,
        )
    if verbose: print(f'sample={sample}', file=sys.stderr)
    assert len(sample) == 1
    return sample[0] #

def get_matched_normal(sample, match_normal, verbose):
    normal = None # default
    if match_normal:
        normal = ii.get_instances(
            endpoint='experiments',
            sample__individual__identifier=sample.individual.identifier,
            technique__slug='DNA|WG|Bulk WGS', # TODO: make as an option
            sample__category="NORMAL",
            is_default_normal=True, # Thanks Eli!
        ) 
        if verbose: print(f'normal={normal}', file=sys.stderr)
    return normal[0] # 

def parse_region(region, n_flanking, verbose):
    chrom, startend = region.split(':')
    if not chrom.startswith('chr'): 
        chrom = 'chr'+chrom.upper().replace('MT', 'M')
    if verbose: print(f'chrom={chrom}, startend={startend}', file=sys.stderr)
    start, end = [int(_) for _ in startend.split('-')]
    assert start <= end
    start = str(start - n_flanking)
    end = str(end + n_flanking)
    if verbose: print(f'start={start}, end={end}', file=sys.stderr)
    return chrom, start, end


def get_matched_bams(sample, normal, verbose):
    identifiers = [sample.identifier, normal.sample.identifier]
    if verbose: print(f'identifiers={identifiers}', file=sys.stderr)
    alignments = ii.get_analyses(
        targets__sample__identifier__in=identifiers,
        application__name='WGS-ALIGNMENT',
        most_recent=True,
    )
    normal_bam_path, tumor_bam_path = None, None
    for alignment in alignments:
        assert len(alignment.targets) == 1
        alignment_sample = alignment.targets[0].sample.identifier
        if verbose: print(f'aligmment sample={alignment_sample}', 
                file=sys.stderr)
        if alignment_sample == normal.sample.identifier:
            normal_bam_path = alignment.results['bam']
        elif alignment_sample == sample.identifier:
            tumor_bam_path = alignment.results['bam']
        else:
            print(f'ERROR: {alignment_sample} is neither normal or tumor')
    assert tumor_bam_path and normal_bam_path
    return tumor_bam_path, normal_bam_path


@click.command()
@click.option('--isabl_sample_id', required=True, multiple=True,
        help="Isabl sample__identifier")
@click.option('--region', required=True,
        help="chr:start-end")
@click.option('--outdir', required=True, default='.', show_default=True,
        help="IGV screenshot output dir")
@click.option('--match_normal', is_flag=True, default=True, show_default=True,
        help="Find and match normal sample")
@click.option('--n_flanking', default=20, show_default=True,
        help="Flanking base-pairs around input region")
@click.option('--verbose', is_flag=True, default=False,
        help="Show inner variables for debugging")
def shoot_igv(isabl_sample_id, region, outdir, match_normal, n_flanking, verbose):
    assert region.count(':') == 1
    assert region.count('-') == 1
    
    for sample_identifier in isabl_sample_id: # assumung n>=1
        sample = get_sample(sample_identifier, verbose)
        normal = get_matched_normal(sample, match_normal, verbose)
        tumor_bam_path, normal_bam_path = get_matched_bams(sample, normal, 
                verbose)
        chrom, start, end = parse_region(region, n_flanking, verbose)
        
        key = (sample.identifier, normal.sample.identifier,
                chrom, start, end)
        keystr = '_'.join(key)
        if not os.path.isdir(outdir):
            try:
                os.system(f'mkdir {outdir}')
            except:
                sys.exit(f"ERROR: cannot make {outdir}")
        tmp_bed_path = os.path.join(outdir, f"_tmp_{keystr}.bed")
        bat_path = os.path.join(outdir, "IGV_snapshots.bat")
        with open(tmp_bed_path, 'w') as tmp_bed:
            line = '\t'.join([chrom, start, end, keystr])
            tmp_bed.write(line + '\n')

        cmd = "module load singularity/3.6.2 && "
        cmd += "singularity exec "
        cmd += '-B /juno ' # TODO: generalize bind dir 
        cmd += "library://soymintc/tools/igvautomator:0.0.1 "
        cmd += "make_IGV_snapshots.py "
        cmd += f"{tumor_bam_path} "
        cmd += f"{normal_bam_path} "
        cmd += f"-o {outdir} "
        cmd += f"-r {tmp_bed_path} "
        cmd += "-group_by_strand "
        cmd += "-nf4 ; " # && -> ; delete even if fails
        cmd += f"rm {tmp_bed_path} ; " # && -> ; delete even if fails
        cmd += f"rm {bat_path}" 
        if verbose: print(f'run command:\n{cmd}', file=sys.stderr)
        os.system(cmd)


if __name__ == '__main__':
    shoot_igv()
