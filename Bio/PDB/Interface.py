# Copyright (C) 2011, Mikael Trellet (mikael.trellet@gmail.com)
# This code is part of the Biopython distribution and governed by its
# license.  Please see the LICENSE file that should have been included
# as part of this package.

"""Interface class, used in Structure objects."""

from Bio.PDB.Entity import Entity
from Bio.Data import IUPACData
from Bio.SCOP.Raf import to_one_letter_code
from Bio.PDB.PDBParser import PDBParser
from Bio.PDB.NACCESS import NACCESS
from Bio.PDB.NACCESS import NACCESS_atomic
from Bio.PDB.Model import Model
from Bio.PDB.Structure import Structure
from Bio.PDB import Superimposer
from Bio.PDB import DSSP
import numpy


class Interface(Entity):
    """
    The Interface object isn't automatically initialize during a PDB parsing,
    but can be guessed from an existing parsed structure in order to analyse
    the interface between 2 or more chains in a complex.
    """

    def __init__(self, id):
        self.level="I"
        self.id=id
        self.neighbors = {}
        self.uniq_pairs = []

        Entity.__init__(self, id)

    # Override Entity add method
    # Interface doesnt follow strictly
    # other Entity rules.
    #
    # Its childs are residues
    # but it may be useful
    # to list them by chain.
    
    def add(self, entity):
        "Add a child to the Entity."

        entity_id=entity.get_id()
        if not self.has_id(entity_id):

            self.child_list.append(entity)
            if entity.parent.id not in self.child_dict:
                self.child_dict[entity.parent.id] = []
            self.child_dict[entity.parent.id].append(entity)

    def get_chains(self):
        "Get the different chains involved in the Interface object"
        for chain in self.child_dict.keys():
            yield chain

    def set_neighbors(self):
        "Creates residues list of neighbors"
        ## Initializes neighbors dictionnary with interface chains
        for c in self.get_chains():
            self.neighbors[c]={}
            
        for resA, resB in self.uniq_pairs:
        ## Checking for 1st residue (if his chain exist, then if 
        ## it is referenced and finally if his partner is already present)
            if resA not in self.neighbors[resA.parent.id]:
                self.neighbors[resA.parent.id][resA]=[]
                self.neighbors[resA.parent.id][resA].append(resB)
            elif resB not in self.neighbors[resA.parent.id][resA]:
                self.neighbors[resA.parent.id][resA].append(resB)
        ## Checking for 2nd residue
            if resB not in self.neighbors[resB.parent.id]:
                self.neighbors[resB.parent.id][resB]=[]
                self.neighbors[resB.parent.id][resB].append(resB)
            elif resA not in self.neighbors[resB.parent.id][resB]:
                self.neighbors[resB.parent.id][resB].append(resA)
        neighbors=self.neighbors
        return neighbors

    def calculate_percentage(self):
        "Gets the percentage of polar/apolar/charged residues at the interface"
        
        polar=0
        apolar=0
        charged=0
        polar_list=getattr(IUPACData, "protein_polarity")
        charged_list=getattr(IUPACData, "protein_pka_side_chain")
        for r in self:
            res=to_one_letter_code[r.resname]
            if res in polar_list['polar']:
                if charged_list[res]:
                    charged=charged+1
                else:
                    polar=polar+1
            else:
                apolar=apolar+1
        print polar, apolar, charged
        polar_percentage=float(polar)/len(self)
        apolar_percentage=float(apolar)/len(self)
        charged_percentage=float(charged)/len(self)
        
        return [polar_percentage, apolar_percentage, charged_percentage]
        
    def _get_atomic_SASA(structure):
        """Retrieves atomic SASA from a NACCESS-submitted structure object"""

        # Ignore Hydrogens otherwise default NACCESS freaks out
        # Maybe add support for flags in the NACCESS module?
        # From the readme:
        # "By default, the program ignores HETATM records, hydrogens, and waters. If you
        # want these to be considered in the calculation supply a parameter of the form
        # -h, -w and/or -y respectively."

        sasa_l = [at.xtra['EXP_NACCESS'] for at in structure.get_atoms() if at.get_parent().id[0] == " " and at.element != 'H']
        sasa = sum(sas_l)
        return sasa
        
    def calculate_BSA(self):
        "Uses NACCESS module in order to calculate the Buried Surface Area"

        # Extract list of chains in the interface only
        chains = list(self.get_chains())
           
        # Create temporary structures to feed NACCESS
        structure_A=Structure("chainA")
        structure_B=Structure("chainB")
        mA = Model(0)
        mB = Model(0)
        mA.add(self.model[chains[0]])
        mB.add(self.model[chains[1]])
        structure_A.add(mA)
        structure_B.add(mB)
        
        # Calculate SASAs
        NACCESS_atomic(self.model)
        NACCESS_atomic(structure_A[0])
        NACCESS_atomic(structure_B[0])

        sas_tot= _get_atomic_SASA(self.model)
        #print 'Accessible surface area, complex:', sas_tot
        sas_A= _get_atomic_SASA(structure_A)
        #print 'Accessible surface aream CHAIN A :', sas_A
        sas_B= _get_atomic_SASA(structure_B)
        #print 'Accessible surface aream CHAIN B :',sas_B
        
        # Calculate BSA
        bsa = sas_A+sas_B-sas_tot
                
        return [bsa, sas_A, sas_B, sas_tot]
        
    def _get_atoms_coords(self, interface, opt):
        "Stores atoms coordinates for both reference and alternate interfaces"
        
        ref_atoms = []
        alt_atoms = []
        
        for ref_res, alt_res in zip(self.child_list, interface.child_list):
            ref_atoms.append(ref_res['CA'])
            alt_atoms.append(alt_res['CA'])
            
        return ref_atoms, alt_atoms
        
    def rmsd(self, mobile, mob_ref=None):
        "Calculates Root Mean Square Deviation between 2 interfaces"
        
        if not mob_ref:
            ref_seq=[to_one_letter_code[r.resname] for r in self.child_list]
            alt_seq=[to_one_letter_code[r.resname] for r in mobile.child_list]
            ref_seq.sort()
            alt_seq.sort()
            print 'REFERENCE', ref_seq
            print 'ALTERNATIVE', alt_seq
            if ref_seq != alt_seq:
                raise ValueError("Sequences doesn't match")
        
        #Build paired lists of c-alpha atoms, ref_atoms and alt_atoms
        #Possibility to calculate RMSD on CA (ca), backbone (bb) or all atoms (all)        
        ref_atoms, alt_atoms = self._get_atoms_coords(mobile, opt="ca")
        
        #Align these paired atom lists:
        super_imposer = Superimposer()
        super_imposer.set_atoms(ref_atoms, alt_atoms)
        
        print "RMS = %0.2f" % super_imposer.rms
        
        return super_imposer.rms
        
    def _get_neighbors_id(self, chain):
        "Creates a dictionary of tuples from the neighbors dictionary"
        
        self.neighbors_id={}
        
        for key in self.neighbors[chain]:
            self.neighbors_id[key.id]=[res.id[1] for res in self.neighbors[chain][key]]
            self.neighbors_id[key.id].sort()        
        
    def fcc(self, mobile):
        "Defined the fraction of native contacts between 2 interfaces"
        
        #Creates neighbors dictionary for each interface residue
        if not self.neighbors:
            self.set_neighbors()
        if not mobile.neighbors:
            mobile.set_neighbors()
        
        #Calculation will be done only one one chain thanks to symetry
        for c in self.get_chains():
            chain=c
            break
        self._get_neighbors_id(chain)
        mobile._get_neighbors_id(chain)
        
        #Gets the number of contacts for the reference interface
        total=sum(len(l) for l in self.neighbors_id.itervalues())
        
        #Finds each common pairs for the 2 interfaces
        common = 0
        for res_id in self.neighbors_id:
            if res_id in mobile.neighbors_id:
                common = common + len(set(self.neighbors_id[res_id]).intersection(set(mobile.neighbors_id[res_id])))
        fcc=float(common/total)
        
        return fcc
